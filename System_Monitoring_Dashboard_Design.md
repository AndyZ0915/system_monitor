# System Monitoring Dashboard — Design Document

**Stack:** Python · Flask · PostgreSQL · Chart.js · WebSockets  
**Timeline:** November 2025 – January 2026  
**Author:** Senior Software Engineer

---

## What We Built and Why

The goal here was pretty straightforward: give teams a single place to watch what their servers are actually doing, in real time, without having to SSH into boxes or dig through logs after something already went wrong. We wanted alerts that fire *before* a disk fills up or CPU spikes kill a service — not after.

The result is a full-stack monitoring app that polls system metrics every 30 seconds, stores everything in PostgreSQL with a 30-day rolling history, and pushes live data to a Chart.js dashboard over WebSockets. It handles 20+ concurrent connections gracefully and fires threshold-based email alerts when things look off.

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Architecture Overview](#2-architecture-overview)
3. [Database Design](#3-database-design)
4. [Metric Collection](#4-metric-collection)
5. [WebSocket Layer](#5-websocket-layer)
6. [Frontend Dashboard](#6-frontend-dashboard)
7. [Alerting System](#7-alerting-system)
8. [API Endpoints](#8-api-endpoints)
9. [Configuration](#9-configuration)
10. [Running the App](#10-running-the-app)
11. [Design Decisions & Tradeoffs](#11-design-decisions--tradeoffs)

---

## 1. Project Structure

```
system_monitor/
├── app/
│   ├── __init__.py          # App factory, SocketIO init
│   ├── models.py            # SQLAlchemy models
│   ├── collector.py         # psutil-based metric collection
│   ├── websocket.py         # WebSocket event handlers
│   ├── routes.py            # HTTP API endpoints
│   ├── alerts.py            # Threshold checks + email dispatch
│   ├── templates/
│   │   └── dashboard.html   # Main dashboard UI
│   └── static/
│       ├── css/style.css
│       └── js/dashboard.js  # Chart.js + Socket.IO client
├── migrations/
│   └── init.sql             # Schema setup
├── config.py                # Config classes (dev/prod)
├── run.py                   # Entry point
├── requirements.txt
└── .env.example
```

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Browser Clients                      │
│              (Chart.js + Socket.IO client)               │
└────────────────────┬────────────────────────────────────┘
                     │ WebSocket / HTTP
┌────────────────────▼────────────────────────────────────┐
│                  Flask Application                        │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  HTTP API   │  │  Socket.IO   │  │  Background   │  │
│  │  (routes)   │  │  (websocket) │  │  Collector    │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  │
│         └────────────────┴──────────────────┘           │
│                          │                               │
│              ┌───────────▼──────────┐                   │
│              │   SQLAlchemy ORM     │                   │
│              └───────────┬──────────┘                   │
└──────────────────────────┼──────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │      PostgreSQL          │
              │  (metrics + alerts)      │
              └─────────────────────────┘
```

The collector runs as a background thread (APScheduler), writing metrics every 30 seconds. The WebSocket layer reads the latest snapshot from the DB and broadcasts it to all connected clients. The alerting engine runs on the same schedule and checks thresholds after each collection cycle.

---

## 3. Database Design

### Tables

**`servers`** — tracks which machines we're monitoring
```sql
CREATE TABLE servers (
    id          SERIAL PRIMARY KEY,
    hostname    VARCHAR(255) UNIQUE NOT NULL,
    ip_address  VARCHAR(45),
    description TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);
```

**`metrics`** — the core time-series table
```sql
CREATE TABLE metrics (
    id          BIGSERIAL PRIMARY KEY,
    server_id   INTEGER REFERENCES servers(id),
    collected_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- CPU
    cpu_percent         FLOAT NOT NULL,
    cpu_count           INTEGER,

    -- Memory
    memory_total        BIGINT,
    memory_used         BIGINT,
    memory_percent      FLOAT NOT NULL,

    -- Disk (primary partition)
    disk_total          BIGINT,
    disk_used           BIGINT,
    disk_percent        FLOAT NOT NULL,

    -- Network (bytes since last poll)
    net_bytes_sent      BIGINT,
    net_bytes_recv      BIGINT,
    net_packets_sent    BIGINT,
    net_packets_recv    BIGINT
);

-- Index for time-range queries (most common access pattern)
CREATE INDEX idx_metrics_server_time ON metrics(server_id, collected_at DESC);

-- Auto-cleanup: drop anything older than 30 days
-- (handled in app via scheduled job, but can also use pg_partman)
```

**`alert_rules`** — configurable thresholds per server
```sql
CREATE TABLE alert_rules (
    id              SERIAL PRIMARY KEY,
    server_id       INTEGER REFERENCES servers(id),
    metric_name     VARCHAR(50) NOT NULL,  -- 'cpu_percent', 'memory_percent', etc.
    threshold       FLOAT NOT NULL,
    comparison      VARCHAR(10) NOT NULL,  -- 'gt', 'lt'
    severity        VARCHAR(20) DEFAULT 'warning',  -- 'warning', 'critical'
    email_to        VARCHAR(255),
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);
```

**`alert_events`** — audit trail of every alert that fired
```sql
CREATE TABLE alert_events (
    id              BIGSERIAL PRIMARY KEY,
    rule_id         INTEGER REFERENCES alert_rules(id),
    server_id       INTEGER REFERENCES servers(id),
    metric_value    FLOAT,
    message         TEXT,
    fired_at        TIMESTAMP DEFAULT NOW(),
    resolved_at     TIMESTAMP,
    notified        BOOLEAN DEFAULT FALSE
);
```

### Data Retention

A scheduled job runs daily to delete metrics older than 30 days:
```sql
DELETE FROM metrics WHERE collected_at < NOW() - INTERVAL '30 days';
```

---

## 4. Metric Collection

The collector uses `psutil` to grab system stats. It runs every 30 seconds via APScheduler and is designed to be non-blocking — if a collection cycle fails (e.g., DB is momentarily unavailable), it logs the error and skips that cycle rather than crashing.

### What we collect per cycle:
- **CPU:** overall utilization percent, core count
- **Memory:** total, used, percent used
- **Disk:** total, used, percent used on the root partition (configurable)
- **Network:** bytes/packets sent and received (delta since last poll)

### Why 30 seconds?
It's a balance. 5 seconds would give smoother charts but generate ~17,000 rows/day per server. 30 seconds gives ~2,880 rows/day, which is easy on storage and still responsive enough for most alerting needs. Teams that need tighter resolution can change `COLLECTION_INTERVAL` in config.

---

## 5. WebSocket Layer

We use **Flask-SocketIO** backed by **eventlet** for async handling. Each connected client joins a room named after the server they're watching.

### Events

| Direction | Event | Payload |
|-----------|-------|---------|
| Server → Client | `metrics_update` | Latest metric snapshot |
| Server → Client | `alert_fired` | Alert details when threshold crossed |
| Client → Server | `subscribe` | `{ server_id: int }` |
| Client → Server | `unsubscribe` | `{ server_id: int }` |

### Broadcast flow
1. Collector writes new metric row to DB
2. Collector calls `broadcast_metrics(server_id, metric_data)`
3. SocketIO emits to all clients in room `server_{id}`
4. Clients update their charts without any polling

### Handling 20+ concurrent connections
- eventlet's green threads handle concurrency cheaply
- Each client is just a room subscription — no per-client state stored in memory
- Metric data is serialized once and broadcast to the whole room (not sent individually)

---

## 6. Frontend Dashboard

The dashboard is a single HTML page served by Flask. It uses **Chart.js** for visualizations and **Socket.IO** for the live data feed.

### Charts

| Metric | Chart Type | History Window |
|--------|-----------|----------------|
| CPU % | Line (real-time) | Last 5 minutes |
| Memory % | Line (real-time) | Last 5 minutes |
| Disk % | Doughnut | Current snapshot |
| Network I/O | Area (stacked) | Last 5 minutes |

### On page load:
1. Fetch last 5 minutes of metrics via REST API (fills in chart history)
2. Connect WebSocket and subscribe to selected server
3. On `metrics_update`, push new data point and shift oldest off the chart

### Multi-server support
A dropdown lets users switch between servers. Switching triggers an unsubscribe/subscribe cycle and reloads chart history for the new server.

---

## 7. Alerting System

The alerting engine runs after each collection cycle. It checks every enabled rule against the freshly collected metric value.

### Alert flow
```
New metric collected
        ↓
For each enabled rule on this server:
    Compare metric_value vs threshold
        ↓
    If threshold crossed:
        Log to alert_events table
        Send email (if not already notified in last N minutes)
        Emit 'alert_fired' via WebSocket
```

### Cooldown logic
We track the last notification time per rule to avoid spamming — if an alert already fired within the last `ALERT_COOLDOWN_MINUTES` (default: 15), we log the event but skip the email.

### Email
Uses Python's `smtplib` with configurable SMTP settings. Emails include: server hostname, metric name, current value, threshold, and timestamp.

### Example rule (via API)
```json
{
  "server_id": 1,
  "metric_name": "cpu_percent",
  "threshold": 85.0,
  "comparison": "gt",
  "severity": "critical",
  "email_to": "ops-team@company.com"
}
```

---

## 8. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/servers` | List all monitored servers |
| POST | `/api/servers` | Register a new server |
| GET | `/api/servers/<id>/metrics` | Time-series metrics (supports `?from=` and `?to=` query params) |
| GET | `/api/servers/<id>/metrics/latest` | Single latest snapshot |
| GET | `/api/servers/<id>/alerts` | Alert history for a server |
| POST | `/api/alert-rules` | Create an alert rule |
| GET | `/api/alert-rules` | List all rules |
| PUT | `/api/alert-rules/<id>` | Update a rule (e.g., change threshold) |
| DELETE | `/api/alert-rules/<id>` | Delete a rule |
| GET | `/` | Dashboard HTML |

---

## 9. Configuration

All configuration lives in `config.py` and is overridden by environment variables (`.env` file in dev).

```python
# Key settings
DATABASE_URL          = "postgresql://user:pass@localhost/sysmonitor"
SECRET_KEY            = "your-secret-key"
COLLECTION_INTERVAL   = 30          # seconds between metric polls
RETENTION_DAYS        = 30          # how long to keep metric history
ALERT_COOLDOWN_MINUTES = 15         # minimum time between repeat alerts

# SMTP (for email alerts)
SMTP_HOST             = "smtp.gmail.com"
SMTP_PORT             = 587
SMTP_USER             = ""
SMTP_PASSWORD         = ""
SMTP_FROM             = "monitor@yourcompany.com"
```

---

## 10. Running the App

### Prerequisites
- Python 3.10+
- PostgreSQL 14+
- pip

### Setup
```bash
# Clone and install deps
git clone <repo>
cd system_monitor
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your DB credentials and SMTP settings

# Initialize database
psql -U postgres -c "CREATE DATABASE sysmonitor;"
psql -U postgres -d sysmonitor -f migrations/init.sql

# Run
python run.py
```

The app starts on `http://localhost:5000` by default.

### Production notes
- Use **gunicorn + eventlet worker** in production: `gunicorn --worker-class eventlet -w 1 run:app`
- Only 1 worker — SocketIO's in-memory state doesn't share across processes (use Redis adapter for multi-worker)
- Put nginx in front for SSL termination and static file serving

---

## 11. Design Decisions & Tradeoffs

**Why PostgreSQL instead of a time-series DB (InfluxDB, TimescaleDB)?**  
For this scale (a handful of servers, 30-second resolution), plain Postgres with a good index on `(server_id, collected_at)` is plenty fast and a lot simpler to operate. We don't need InfluxDB's compression or downsampling features at 30-day retention.

**Why Flask-SocketIO instead of a message broker (Redis Pub/Sub, Kafka)?**  
The team wanted minimal infrastructure. Flask-SocketIO handles the push requirements without adding a Redis or Kafka dependency. If this scales to dozens of servers with hundreds of clients, moving to Redis adapter for SocketIO would be the right next step.

**Why in-process APScheduler instead of Celery?**  
Same reasoning — fewer moving parts. The collection job is lightweight and running it in-process is fine for a single-instance deployment. Celery makes sense if collection becomes slow (e.g., many remote servers via SNMP) or we need distributed workers.

**Why 30-day retention?**  
Enough history for monthly trend analysis and incident post-mortems without the DB growing unbounded. Teams can bump `RETENTION_DAYS` if they want longer history, but should watch storage.

**Why Chart.js instead of Grafana/D3?**  
Grafana would be overkill and adds another service. D3 gives more flexibility but requires significantly more code. Chart.js hits the sweet spot for readable, maintainable dashboard code that a junior dev can understand and extend.

---

*Last updated: January 2026*
