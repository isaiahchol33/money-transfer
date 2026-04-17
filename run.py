import os
from app import create_app

app = create_app()

# For Gunicorn (Render uses this)
if __name__ != "__main__":
    application = app

# Local dev only
if __name__ == "__main__":
    from app import socketio

    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
        use_reloader=False
    )