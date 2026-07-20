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

The app starts on `http://localhost:5000`.

## Security note

⚠️ This project currently ships with a `.env` file containing real-looking
credentials (DB password, SMTP placeholders). If this repo has ever been
pushed anywhere, **rotate the database password immediately** and remove
`.env` from git history (e.g. with `git filter-repo` or BFG). `.gitignore`
now excludes `.env` going forward, but that only prevents *future* commits —
it does not retroactively scrub history.
