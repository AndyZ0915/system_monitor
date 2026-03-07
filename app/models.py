from datetime import datetime
from app import db


class Server(db.Model):
    __tablename__ = "servers"

    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(255), unique=True, nullable=False)
    ip_address = db.Column(db.String(45))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    metrics = db.relationship("Metric", back_populates="server", lazy="dynamic")
    alert_rules = db.relationship("AlertRule", back_populates="server", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }


class Metric(db.Model):
    __tablename__ = "metrics"

    id = db.Column(db.BigInteger, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey("servers.id"), nullable=False)
    collected_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    cpu_percent = db.Column(db.Float, nullable=False)
    cpu_count = db.Column(db.Integer)

    memory_total = db.Column(db.BigInteger)
    memory_used = db.Column(db.BigInteger)
    memory_percent = db.Column(db.Float, nullable=False)

    disk_total = db.Column(db.BigInteger)
    disk_used = db.Column(db.BigInteger)
    disk_percent = db.Column(db.Float, nullable=False)

    net_bytes_sent = db.Column(db.BigInteger)
    net_bytes_recv = db.Column(db.BigInteger)
    net_packets_sent = db.Column(db.BigInteger)
    net_packets_recv = db.Column(db.BigInteger)

    server = db.relationship("Server", back_populates="metrics")

    def to_dict(self):
        return {
            "id": self.id,
            "server_id": self.server_id,
            "collected_at": self.collected_at.isoformat(),
            "cpu_percent": self.cpu_percent,
            "cpu_count": self.cpu_count,
            "memory_total": self.memory_total,
            "memory_used": self.memory_used,
            "memory_percent": self.memory_percent,
            "disk_total": self.disk_total,
            "disk_used": self.disk_used,
            "disk_percent": self.disk_percent,
            "net_bytes_sent": self.net_bytes_sent,
            "net_bytes_recv": self.net_bytes_recv,
            "net_packets_sent": self.net_packets_sent,
            "net_packets_recv": self.net_packets_recv,
        }


class AlertRule(db.Model):
    __tablename__ = "alert_rules"

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey("servers.id"), nullable=False)
    metric_name = db.Column(db.String(50), nullable=False)
    threshold = db.Column(db.Float, nullable=False)
    comparison = db.Column(db.String(10), nullable=False)  # 'gt' or 'lt'
    severity = db.Column(db.String(20), default="warning")
    email_to = db.Column(db.String(255))
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    server = db.relationship("Server", back_populates="alert_rules")
    events = db.relationship("AlertEvent", back_populates="rule", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.id,
            "server_id": self.server_id,
            "metric_name": self.metric_name,
            "threshold": self.threshold,
            "comparison": self.comparison,
            "severity": self.severity,
            "email_to": self.email_to,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
        }


class AlertEvent(db.Model):
    __tablename__ = "alert_events"

    id = db.Column(db.BigInteger, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("alert_rules.id"), nullable=False)
    server_id = db.Column(db.Integer, db.ForeignKey("servers.id"), nullable=False)
    metric_value = db.Column(db.Float)
    message = db.Column(db.Text)
    fired_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    notified = db.Column(db.Boolean, default=False)

    rule = db.relationship("AlertRule", back_populates="events")

    def to_dict(self):
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "server_id": self.server_id,
            "metric_value": self.metric_value,
            "message": self.message,
            "fired_at": self.fired_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "notified": self.notified,
        }
