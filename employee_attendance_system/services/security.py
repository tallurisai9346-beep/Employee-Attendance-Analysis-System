from functools import wraps

from flask import abort, redirect, session, url_for


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            if not session.get("admin_id") and not session.get("employee_id"):
                return redirect(url_for("auth.admin_login"))
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def employee_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "employee":
            if not session.get("admin_id") and not session.get("employee_id"):
                return redirect(url_for("auth.employee_login"))
            abort(403)
        return view(*args, **kwargs)
    return wrapped