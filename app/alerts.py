import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app import db, socketio
from app.models import AlertRule, AlertEvent

logger = logging.getLogger(__name__)


def check_alerts(app, server_id, metric_data):
    """Check all enabled alert rules for this server against fresh metric data."""
    with app.app_context():
        rules = AlertRule.query.filter_by(server_id=server_id, enabled=True).all()

        for rule in rules:
            value = metric_data.get(rule.metric_name)
            if value is None:
                continue

            triggered = (
                (rule.comparison == "gt" and value > rule.threshold)
                or (rule.comparison == "lt" and value < rule.threshold)
            )

            if not triggered:
                continue

            message = (
                f"[{rule.severity.upper()}] {rule.metric_name} is {value:.1f} "
                f"(threshold: {rule.comparison} {rule.threshold}) "
                f"on server {server_id}"
            )

            # Log the event
            event = AlertEvent(
                rule_id=rule.id,
                server_id=server_id,
                metric_value=value,
                message=message,
            )
            db.session.add(event)

            # Check cooldown — don't spam notifications
            cooldown_minutes = app.config.get("ALERT_COOLDOWN_MINUTES", 15)
            recent_notification = (
                AlertEvent.query.filter_by(rule_id=rule.id, notified=True)
                .filter(
                    AlertEvent.fired_at > datetime.utcnow() - timedelta(minutes=cooldown_minutes)
                )
                .first()
            )

            if not recent_notification:
                event.notified = True
                _send_email_alert(app, rule, message, value)
                # Push to dashboard
                socketio.emit(
                    "alert_fired",
                    {
                        "server_id": server_id,
                        "rule_id": rule.id,
                        "metric_name": rule.metric_name,
                        "value": value,
                        "threshold": rule.threshold,
                        "severity": rule.severity,
                        "message": message,
                        "fired_at": datetime.utcnow().isoformat(),
                    },
                    room=f"server_{server_id}",
                )

            db.session.commit()
            logger.warning(message)


def _send_email_alert(app, rule, message, value):
    """Send an email notification for a triggered alert rule."""
    if not rule.email_to:
        return

    smtp_host = app.config.get("SMTP_HOST", "")
    smtp_user = app.config.get("SMTP_USER", "")
    smtp_password = app.config.get("SMTP_PASSWORD", "")
    smtp_from = app.config.get("SMTP_FROM", "monitor@localhost")
    smtp_port = app.config.get("SMTP_PORT", 587)

    if not smtp_host or not smtp_user:
        logger.warning("SMTP not configured — skipping email alert")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[{rule.severity.upper()}] Alert: {rule.metric_name} threshold exceeded"
        msg["From"] = smtp_from
        msg["To"] = rule.email_to

        html_body = f"""
        <html><body>
        <h2 style="color: {'#e74c3c' if rule.severity == 'critical' else '#f39c12'};">
            System Alert — {rule.severity.upper()}
        </h2>
        <p>{message}</p>
        <table style="border-collapse:collapse; font-family:monospace;">
            <tr><td style="padding:4px 12px;"><b>Metric</b></td><td>{rule.metric_name}</td></tr>
            <tr><td style="padding:4px 12px;"><b>Current Value</b></td><td>{value:.2f}</td></tr>
            <tr><td style="padding:4px 12px;"><b>Threshold</b></td>
                <td>{rule.comparison} {rule.threshold}</td></tr>
            <tr><td style="padding:4px 12px;"><b>Time</b></td>
                <td>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</td></tr>
        </table>
        </body></html>
        """

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, rule.email_to, msg.as_string())

        logger.info(f"Alert email sent to {rule.email_to}")

    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
