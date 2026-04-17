import os
from app import create_app, socketio

# Create Flask app
app = create_app()

# =========================
# 🔥 DEVELOPMENT ONLY
# =========================
if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
        use_reloader=False,
        log_output=True
    )