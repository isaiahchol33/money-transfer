import os

print("🚀 Starting app...")

try:
    from app import create_app
    print("✅ Imported create_app")
except Exception as e:
    print("🔥 IMPORT ERROR:", e)
    raise

try:
    app = create_app()
    print("✅ App created successfully")
except Exception as e:
    print("🔥 APP CREATION ERROR:", e)
    raise

if __name__ == "__main__":
    from app import socketio

    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
        use_reloader=False
    )