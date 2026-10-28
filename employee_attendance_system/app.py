import os
import secrets
import time
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, abort, flash, redirect, render_template, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash

from config import Config
from models import AdminAccount, Attendance, Department, Employee, Holiday, LeaveRequest, db
from routes.admin import admin_bp
from routes.auth import auth_bp
from routes.employee import employee_bp

csrf = CSRFProtect()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)
    csrf.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(employee_bp, url_prefix="/employee")

    @app.before_request
    def enforce_session_timeout():
        if session.get("role"):
            now = time.time()
            last_seen = session.get("last_seen", now)
            if now - last_seen > app.config["PERMANENT_SESSION_LIFETIME"].total_seconds():
                session.clear()
                flash("Your session expired. Please sign in again.", "warning")
                return redirect(url_for("auth.landing"))
            session["last_seen"] = now
            session.permanent = True

    @app.context_processor
    def inject_globals():
        from flask_wtf.csrf import generate_csrf
        return {"csrf_token": generate_csrf, "today": date.today()}

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403, title="Access denied", message="You do not have permission to view this page."), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, title="Page not found", message="The page you requested could not be found."), 404

    with app.app_context():
        db.create_all()
        if not app.config.get("TESTING"):
            seed_database()

    @app.cli.command("set-admin-credentials")
    def set_admin_credentials():
        username = os.getenv("ADMIN_USERNAME", "").strip()
        password = os.getenv("ADMIN_PASSWORD", "")
        if not username or len(password) < 12:
            raise SystemExit("Set ADMIN_USERNAME and an ADMIN_PASSWORD of at least 12 characters first.")
        account = AdminAccount.query.first()
        if account is None:
            account = AdminAccount(username=username, full_name="System Administrator", password_hash=generate_password_hash(password))
            db.session.add(account)
        else:
            account.username = username
            account.password_hash = generate_password_hash(password)
        db.session.commit()
        print("Admin credentials stored as a password hash.")

    return app


def seed_database():
    if not Department.query.first():
        db.session.add_all([Department(department_name=name) for name in ("Engineering", "People", "Finance", "Operations")])
        db.session.commit()
    if not AdminAccount.query.first():
        username = os.getenv("ADMIN_USERNAME", "admin")
        password = os.getenv("ADMIN_PASSWORD") or secrets.token_urlsafe(18)
        admin = AdminAccount(username=username, full_name="System Administrator", password_hash=generate_password_hash(password))
        db.session.add(admin)
        db.session.commit()
        print(f"Initial admin created: {username}")
        if not os.getenv("ADMIN_PASSWORD"):
            print(f"Temporary admin password (shown once): {password}")
    if not Employee.query.first():
        department = Department.query.order_by(Department.id).first()
        demo_password = os.getenv("DEMO_EMPLOYEE_PASSWORD") or secrets.token_urlsafe(16)
        samples = [
            ("EMP-1001", "Maya Chen", "maya.chen@example.test", "Software Engineer"),
            ("EMP-1002", "Noah Patel", "noah.patel@example.test", "People Partner"),
            ("EMP-1003", "Ava Brooks", "ava.brooks@example.test", "Financial Analyst"),
        ]
        employees = []
        for index, (code, name, email, title) in enumerate(samples):
            employees.append(Employee(
                employee_code=code,
                full_name=name,
                email=email,
                department_id=department.id,
                designation=title,
                joining_date=date.today() - timedelta(days=180 + index * 90),
                password_hash=generate_password_hash(demo_password),
                account_status="active",
            ))
        db.session.add_all(employees)
        db.session.commit()
        print("Demo employee usernames: maya.chen@example.test, noah.patel@example.test, ava.brooks@example.test")
        if not os.getenv("DEMO_EMPLOYEE_PASSWORD"):
            print(f"Temporary employee password (shown once): {demo_password}")
        start = date.today() - timedelta(days=34)
        for employee in employees:
            current = start
            while current <= date.today():
                if current.weekday() < 5:
                    db.session.add(Attendance(employee_id=employee.id, attendance_date=current, status="Present" if current.day % 9 else "Absent"))
                current += timedelta(days=1)
        db.session.add(LeaveRequest(
            employee_id=employees[0].id,
            leave_type="Personal",
            start_date=date.today() + timedelta(days=7),
            end_date=date.today() + timedelta(days=8),
            reason="Personal commitment",
        ))
        db.session.commit()


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")