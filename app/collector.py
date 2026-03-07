import logging
import socket
from datetime import datetime, timedelta

import psutil
from apscheduler.schedulers.background import BackgroundScheduler

from app import db, socketio
from app.models import Metric, Server

logger = logging.getLogger(__name__)

# Track previous network counters to calculate per-interval deltas
_prev_net_counters = {}


def get_or_create_server(app):
    # registers this machine in the DB if it hasn't been seen before
    hostname = socket.gethostname()
    try:
        ip = socket.gethostbyname(hostname)
    except Exception:
        ip = "127.0.0.1"

    with app.app_context():
        server = Server.query.filter_by(hostname=hostname).first()
        if not server:
            server = Server(hostname=hostname, ip_address=ip, description="Local machine")
            db.session.add(server)
            db.session.commit()
            logger.info(f"Registered new server: {hostname}")
        return server.id


def collect_metrics(app, server_id):
    # pulls current system stats and writes them to the DB
    global _prev_net_counters

    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()

        # Calculate delta since last poll
        prev = _prev_net_counters.get(server_id, {})
        net_bytes_sent = net.bytes_sent - prev.get("bytes_sent", net.bytes_sent)
        net_bytes_recv = net.bytes_recv - prev.get("bytes_recv", net.bytes_recv)
        net_packets_sent = net.packets_sent - prev.get("packets_sent", net.packets_sent)
        net_packets_recv = net.packets_recv - prev.get("packets_recv", net.packets_recv)

        _prev_net_counters[server_id] = {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        }

        metric_data = {
            "server_id": server_id,
            "collected_at": datetime.utcnow().isoformat(),
            "cpu_percent": cpu_percent,
            "cpu_count": cpu_count,
            "memory_total": mem.total,
            "memory_used": mem.used,
            "memory_percent": mem.percent,
            "disk_total": disk.total,
            "disk_used": disk.used,
            "disk_percent": disk.percent,
            "net_bytes_sent": max(0, net_bytes_sent),
            "net_bytes_recv": max(0, net_bytes_recv),
            "net_packets_sent": max(0, net_packets_sent),
            "net_packets_recv": max(0, net_packets_recv),
        }

        with app.app_context():
            m = Metric(**metric_data)
            db.session.add(m)
            db.session.commit()

            # Broadcast to all WebSocket clients watching this server
            socketio.emit(
                "metrics_update",
                metric_data,
                room=f"server_{server_id}",
            )

            # Check alert rules
            from app.alerts import check_alerts
            check_alerts(app, server_id, metric_data)

        logger.debug(f"Collected metrics for server {server_id}: CPU={cpu_percent}%")

    except Exception as e:
        logger.error(f"Failed to collect metrics for server {server_id}: {e}")


def purge_old_metrics(app):
    # deletes rows older than the configured retention window, runs daily
    try:
        with app.app_context():
            retention_days = app.config.get("RETENTION_DAYS", 30)
            cutoff = datetime.utcnow() - timedelta(days=retention_days)
            deleted = Metric.query.filter(Metric.collected_at < cutoff).delete()
            db.session.commit()
            if deleted:
                logger.info(f"Purged {deleted} metric rows older than {retention_days} days")
    except Exception as e:
        logger.error(f"Failed to purge old metrics: {e}")


def start_collector(app):
    # starts the background scheduler for metric collection and cleanup
    with app.app_context():
        # Make sure tables exist
        db.create_all()
        server_id = get_or_create_server(app)

    interval = app.config.get("COLLECTION_INTERVAL", 30)

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=collect_metrics,
        args=[app, server_id],
        trigger="interval",
        seconds=interval,
        id="collect_metrics",
        replace_existing=True,
    )
    scheduler.add_job(
        func=purge_old_metrics,
        args=[app],
        trigger="interval",
        hours=24,
        id="purge_metrics",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Collector started — polling every {interval}s")
