-- System Monitor — initial schema
-- Run: psql -U postgres -d sysmonitor -f migrations/init.sql

CREATE TABLE IF NOT EXISTS servers (
    id          SERIAL PRIMARY KEY,
    hostname    VARCHAR(255) UNIQUE NOT NULL,
    ip_address  VARCHAR(45),
    description TEXT,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS metrics (
    id              BIGSERIAL PRIMARY KEY,
    server_id       INTEGER REFERENCES servers(id) ON DELETE CASCADE,
    collected_at    TIMESTAMP NOT NULL DEFAULT NOW(),

    cpu_percent     FLOAT NOT NULL,
    cpu_count       INTEGER,

    memory_total    BIGINT,
    memory_used     BIGINT,
    memory_percent  FLOAT NOT NULL,

    disk_total      BIGINT,
    disk_used       BIGINT,
    disk_percent    FLOAT NOT NULL,

    net_bytes_sent   BIGINT,
    net_bytes_recv   BIGINT,
    net_packets_sent BIGINT,
    net_packets_recv BIGINT
);

CREATE INDEX IF NOT EXISTS idx_metrics_server_time
    ON metrics(server_id, collected_at DESC);

CREATE TABLE IF NOT EXISTS alert_rules (
    id          SERIAL PRIMARY KEY,
    server_id   INTEGER REFERENCES servers(id) ON DELETE CASCADE,
    metric_name VARCHAR(50) NOT NULL,
    threshold   FLOAT NOT NULL,
    comparison  VARCHAR(10) NOT NULL,
    severity    VARCHAR(20) DEFAULT 'warning',
    email_to    VARCHAR(255),
    enabled     BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alert_events (
    id           BIGSERIAL PRIMARY KEY,
    rule_id      INTEGER REFERENCES alert_rules(id) ON DELETE CASCADE,
    server_id    INTEGER REFERENCES servers(id) ON DELETE CASCADE,
    metric_value FLOAT,
    message      TEXT,
    fired_at     TIMESTAMP DEFAULT NOW(),
    resolved_at  TIMESTAMP,
    notified     BOOLEAN DEFAULT FALSE
);

-- Seed a default alert rule (optional example)
-- INSERT INTO alert_rules (server_id, metric_name, threshold, comparison, severity)
-- SELECT 1, 'cpu_percent', 85.0, 'gt', 'critical'
-- WHERE EXISTS (SELECT 1 FROM servers WHERE id = 1);
