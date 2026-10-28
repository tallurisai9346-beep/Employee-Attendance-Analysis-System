from flask import session

from models import ActivityLog, db


def log_activity(action, details=""):
    actor_role = session.get("role", "system")
    actor_id = session.get("admin_id") or session.get("employee_id") or 0
    db.session.add(ActivityLog(actor_role=actor_role, actor_id=actor_id, action=action, details=details[:500]))