import os
from app import create_app, socketio

app = create_app()

# 👇 IMPORTANT: expose Flask app for gunicorn
application = app

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
        use_reloader=False
    )