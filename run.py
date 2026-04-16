import eventlet
eventlet.monkey_patch()

from app import create_app, socketio

app = create_app()

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False,   # 🔥 prevents duplicate socket connections in dev
        log_output=True
    )