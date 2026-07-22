# System Monitor

Real-time server monitoring dashboard — Flask + PostgreSQL + Chart.js, with
threshold-based email alerts pushed live over WebSockets.

See [`System_Monitoring_Dashboard_Design.md`](System_Monitoring_Dashboard_Design.md)
for full architecture, schema, and API details.

## Quickstart

```bash
# Install deps
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your own DB credentials and SMTP settings —
# never commit .env, it's already in .gitignore

# Initialize the database
psql -U postgres -c "CREATE DATABASE sysmonitor;"
psql -U postgres -d sysmonitor -f migrations/init.sql

# Run
python run.py
```

