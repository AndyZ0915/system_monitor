from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request, render_template, current_app

from app import db
from app.models import Server, Metric, AlertRule, AlertEvent

bp = Blueprint("main", __name__)


# ─── Dashboard ────────────────────────────────────────────────────────────────

@bp.route("/")
def dashboard():
    servers = Server.query.order_by(Server.hostname).all()
    return render_template("dashboard.html", servers=servers)


# ─── Servers ──────────────────────────────────────────────────────────────────

@bp.route("/api/servers", methods=["GET"])
def list_servers():
    servers = Server.query.order_by(Server.hostname).all()
    return jsonify([s.to_dict() for s in servers])


@bp.route("/api/servers", methods=["POST"])
def create_server():
    data = request.json
    if not data or not data.get("hostname"):
        return jsonify({"error": "hostname is required"}), 400

    if Server.query.filter_by(hostname=data["hostname"]).first():
        return jsonify({"error": "server already exists"}), 409

    server = Server(
        hostname=data["hostname"],
        ip_address=data.get("ip_address"),
        description=data.get("description"),
    )
    db.session.add(server)
    db.session.commit()
    return jsonify(server.to_dict()), 201


# ─── Metrics ──────────────────────────────────────────────────────────────────

@bp.route("/api/servers/<int:server_id>/metrics", methods=["GET"])
def get_metrics(server_id):
    server = Server.query.get_or_404(server_id)

    # Default: last hour. Supports ?from= and ?to= as ISO timestamps.
    from_str = request.args.get("from")
    to_str = request.args.get("to")

    # CHANGE: wrapped in try/except — fromisoformat() raised an unhandled
    # ValueError (500) on a malformed ?from=/?to=, now returns a clean 400
    try:
        from_dt = datetime.fromisoformat(from_str) if from_str else datetime.utcnow() - timedelta(hours=1)
        to_dt = datetime.fromisoformat(to_str) if to_str else datetime.utcnow()
    except ValueError:
        return jsonify({"error": "from/to must be valid ISO timestamps"}), 400

    metrics = (
        Metric.query.filter(
            Metric.server_id == server_id,
            Metric.collected_at >= from_dt,
            Metric.collected_at <= to_dt,
        )
        .order_by(Metric.collected_at.asc())
        .all()
    )
    return jsonify([m.to_dict() for m in metrics])


@bp.route("/api/servers/<int:server_id>/metrics/latest", methods=["GET"])
def get_latest_metric(server_id):
    Server.query.get_or_404(server_id)
    metric = (
        Metric.query.filter_by(server_id=server_id)
        .order_by(Metric.collected_at.desc())
        .first()
    )
    if not metric:
        return jsonify({"error": "no metrics found"}), 404
    return jsonify(metric.to_dict())


# ─── Alert Rules ──────────────────────────────────────────────────────────────

@bp.route("/api/alert-rules", methods=["GET"])
def list_alert_rules():
    server_id = request.args.get("server_id", type=int)
    query = AlertRule.query
    if server_id:
        query = query.filter_by(server_id=server_id)
    rules = query.order_by(AlertRule.created_at.desc()).all()
    return jsonify([r.to_dict() for r in rules])


# CHANGE: shared severity whitelist — the frontend only styles 'critical'
# specially, so a typo'd severity here would silently break that
VALID_SEVERITIES = ["info", "warning", "critical"]


@bp.route("/api/alert-rules", methods=["POST"])
def create_alert_rule():
    data = request.json
    # CHANGE: request.json is None for a JSON 'null' body and a list for a
    # JSON array body — either used to blow up on data["metric_name"] etc.
    # with an unhandled TypeError (500) instead of a clean 400
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    required = ["server_id", "metric_name", "threshold", "comparison"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"{field} is required"}), 400

    valid_metrics = ["cpu_percent", "memory_percent", "disk_percent"]
    if data["metric_name"] not in valid_metrics:
        return jsonify({"error": f"metric_name must be one of {valid_metrics}"}), 400

    if data["comparison"] not in ("gt", "lt"):
        return jsonify({"error": "comparison must be 'gt' or 'lt'"}), 400

    # CHANGE: validate severity so bad values don't silently fall through
    severity = data.get("severity", "warning")
    if severity not in VALID_SEVERITIES:
        return jsonify({"error": f"severity must be one of {VALID_SEVERITIES}"}), 400

    # CHANGE: threshold was passed straight to float() below — a
    # non-numeric value raised an unhandled ValueError (500)
    try:
        threshold = float(data["threshold"])
    except (TypeError, ValueError):
        return jsonify({"error": "threshold must be a number"}), 400

    Server.query.get_or_404(data["server_id"])

    rule = AlertRule(
        server_id=data["server_id"],
        metric_name=data["metric_name"],
        threshold=threshold,
        comparison=data["comparison"],
        severity=severity,
        email_to=data.get("email_to"),
        enabled=data.get("enabled", True),
    )
    db.session.add(rule)
    db.session.commit()
    return jsonify(rule.to_dict()), 201


@bp.route("/api/alert-rules/<int:rule_id>", methods=["PUT"])
def update_alert_rule(rule_id):
    rule = AlertRule.query.get_or_404(rule_id)
    data = request.json
    # CHANGE: data was used directly in `for field in [...]: if field in data`
    # with no None/type check — a JSON 'null' or array body raised an
    # unhandled TypeError (500) instead of a clean 400
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    # CHANGE: PUT accepted any value for comparison/severity/threshold with
    # no validation, unlike POST — added the same checks here for consistency
    if "comparison" in data and data["comparison"] not in ("gt", "lt"):
        return jsonify({"error": "comparison must be 'gt' or 'lt'"}), 400

    if "severity" in data and data["severity"] not in VALID_SEVERITIES:
        return jsonify({"error": f"severity must be one of {VALID_SEVERITIES}"}), 400

    if "threshold" in data:
        try:
            data["threshold"] = float(data["threshold"])
        except (TypeError, ValueError):
            return jsonify({"error": "threshold must be a number"}), 400

    for field in ["threshold", "comparison", "severity", "email_to", "enabled"]:
        if field in data:
            setattr(rule, field, data[field])

    db.session.commit()
    return jsonify(rule.to_dict())


@bp.route("/api/alert-rules/<int:rule_id>", methods=["DELETE"])
def delete_alert_rule(rule_id):
    rule = AlertRule.query.get_or_404(rule_id)
    db.session.delete(rule)
    db.session.commit()
    return jsonify({"deleted": rule_id})


# ─── Alert Events ─────────────────────────────────────────────────────────────

@bp.route("/api/servers/<int:server_id>/alerts", methods=["GET"])
def get_alert_events(server_id):
    Server.query.get_or_404(server_id)
    events = (
        AlertEvent.query.filter_by(server_id=server_id)
        .order_by(AlertEvent.fired_at.desc())
        .limit(100)
        .all()
    )
    return jsonify([e.to_dict() for e in events])
