import eventlet
eventlet.monkey_patch()

import logging
import os

from app import create_app, socketio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = create_app(os.environ.get("FLASK_ENV", "default"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  System Monitor running at http://localhost:{port}\n")
    socketio.run(app, host="0.0.0.0", port=port, debug=app.debug)
