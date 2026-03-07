from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from config import config

db = SQLAlchemy()
socketio = SocketIO()


def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    socketio.init_app(app, async_mode="eventlet", cors_allowed_origins="*")

    with app.app_context():
        from app.routes import bp as routes_bp
        app.register_blueprint(routes_bp)

        from app import websocket  # noqa — registers SocketIO event handlers
        from app.collector import start_collector
        start_collector(app)

    return app
