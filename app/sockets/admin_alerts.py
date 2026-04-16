from app import socketio
from flask_socketio import join_room, leave_room
from flask_login import current_user


# ================= ROOM NAME =================
ADMIN_ROOM = "admins"


# ================= CONNECT =================
@socketio.on('connect', namespace='/admin')
def admin_connect():
    """
    When user connects to /admin namespace
    → join admins room if admin
    """
    try:
        if current_user.is_authenticated and getattr(current_user, "is_admin", False):
            join_room(ADMIN_ROOM)
            print(f"[SOCKET] Admin joined room: {current_user.id}")
        else:
            print("[SOCKET] Non-admin tried to connect")
    except Exception as e:
        print("Socket connect error:", e)


# ================= DISCONNECT =================
@socketio.on('disconnect', namespace='/admin')
def admin_disconnect():
    try:
        if current_user.is_authenticated:
            leave_room(ADMIN_ROOM)
            print(f"[SOCKET] Admin left room: {current_user.id}")
    except Exception as e:
        print("Socket disconnect error:", e)


# ================= SAFE JSON =================
def make_json_safe(data):
    safe = {}

    if isinstance(data, dict):
        for k, v in data.items():
            try:
                if v is None:
                    safe[k] = ""
                elif isinstance(v, (str, int, float, bool)):
                    safe[k] = v
                else:
                    safe[k] = str(v)
            except Exception:
                safe[k] = str(v)

    return safe


# ================= MAIN EMITTER =================
def send_admin_alert(title, data=None, trigger_dashboard=True):
    """
    Send alert ONLY to admins
    + trigger dashboard refresh
    """

    payload = {
        "title": str(title or "Alert"),
        "payload": make_json_safe(data)
    }

    # 🔔 Alert event
    socketio.emit(
        "admin_alert",
        payload,
        namespace="/admin",
        room=ADMIN_ROOM
    )

    # 🔄 Dashboard refresh event
    if trigger_dashboard:
        socketio.emit(
            "dashboard_update",
            {"status": "updated"},
            namespace="/admin",
            room=ADMIN_ROOM
        )