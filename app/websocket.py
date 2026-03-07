import logging
from flask_socketio import join_room, leave_room, emit

from app import socketio

logger = logging.getLogger(__name__)


@socketio.on("connect")
def handle_connect():
    logger.debug("Client connected")
    emit("connected", {"status": "ok"})


@socketio.on("disconnect")
def handle_disconnect():
    logger.debug("Client disconnected")


@socketio.on("subscribe")
def handle_subscribe(data):
    server_id = data.get("server_id")
    if not server_id:
        emit("error", {"message": "server_id required"})
        return

    room = f"server_{server_id}"
    join_room(room)
    logger.debug(f"Client subscribed to {room}")
    emit("subscribed", {"server_id": server_id, "room": room})


@socketio.on("unsubscribe")
def handle_unsubscribe(data):
    server_id = data.get("server_id")
    if not server_id:
        return

    room = f"server_{server_id}"
    leave_room(room)
    logger.debug(f"Client unsubscribed from {room}")
    emit("unsubscribed", {"server_id": server_id})
