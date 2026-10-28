import secrets
from datetime import date

from email_validator import EmailNotValidError, validate_email
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from models import AdminAccount, Department, Employee, db
from services.activity import log_activity


auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/")
def landing():
    if session.get("role") == "admin":
        return redirect(url_for("admin.dashboard"))
    if session.get("role") == "employee":
        return redirect(url_for("employee.dashboard"))
    return render_template("landing.html")


@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("role") == "admin":
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        account = AdminAccount.query.filter_by(username=username).first()
        if account and check_password_hash(account.password_hash, password):
            session.clear()
            session.permanent = True
            session["role"] = "admin"
            session["admin_id"] = account.id
            session["display_name"] = account.full_name
            return redirect(url_for("admin.dashboard"))
        flash("Admin username or password was not recognized.", "danger")
    return render_template("auth/login.html", portal="admin")


@auth_bp.route("/employee/login", methods=["GET", "POST"])
def employee_login():
    if session.get("role") == "admin":
        return redirect(url_for("admin.dashboard"))
    if session.get("role") == "employee":
        return redirect(url_for("employee.dashboard"))
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        employee = Employee.query.filter(
            db_or(Employee.email == identifier.lower(), Employee.employee_code == identifier.upper())
        ).first()
        if employee and employee.account_status == "active" and check_password_hash(employee.password_hash, password):
            session.clear()
            session.permanent = True
            session["role"] = "employee"
            session["employee_id"] = employee.id
            session["display_name"] = employee.full_name
            return redirect(url_for("employee.dashboard"))
        flash("Employee email/ID or password was not recognized.", "danger")
    return render_template("auth/login.html", portal="employee")


@auth_bp.route("/employee/signup", methods=["GET", "POST"])
def employee_signup():
    if session.get("role") == "admin":
        return redirect(url_for("admin.dashboard"))
    if session.get("role") == "employee":
        return redirect(url_for("employee.dashboard"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        try:
            validated_email = validate_email(email, check_deliverability=False).normalized
            if not full_name or len(full_name) > 100:
                raise ValueError("Enter your name using no more than 100 characters.")
            if len(phone) > 30:
                raise ValueError("Phone number must be 30 characters or fewer.")
            if len(password) < 12:
                raise ValueError("Password must contain at least 12 characters.")
            if password != confirm_password:
                raise ValueError("The passwords do not match.")
        except (EmailNotValidError, ValueError) as exc:
            flash(str(exc), "danger")
            return render_template("auth/signup.html", full_name=full_name, email=email, phone=phone)

        if Employee.query.filter_by(email=validated_email).first():
            flash("An account with that email already exists. Sign in or contact an administrator.", "danger")
            return render_template("auth/signup.html", full_name=full_name, email=email, phone=phone)

        department = Department.query.filter_by(department_name="Unassigned").first()
        if department is None:
            department = Department(department_name="Unassigned")
            db.session.add(department)
            db.session.flush()

        employee_code = ""
        for _ in range(5):
            candidate = f"NEW-{secrets.token_hex(4).upper()}"
            if not Employee.query.filter_by(employee_code=candidate).first():
                employee_code = candidate
                break
        if not employee_code:
            db.session.rollback()
            raise RuntimeError("Could not generate a unique employee code for the new account.")

        employee = Employee(
            employee_code=employee_code,
            full_name=full_name,
            email=validated_email,
            phone=phone,
            department_id=department.id,
            designation="Employee",
            joining_date=date.today(),
            password_hash=generate_password_hash(password),
        )
        db.session.add(employee)
        try:
            log_activity("employee_self_registered", employee_code)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("An account with those details already exists. Please sign in or try another email.", "danger")
            return render_template("auth/signup.html", full_name=full_name, email=email, phone=phone)

        session.clear()
        session.permanent = True
        session["role"] = "employee"
        session["employee_id"] = employee.id
        session["display_name"] = employee.full_name
        flash(f"Account created. Your employee ID is {employee_code}.", "success")
        return redirect(url_for("employee.dashboard"))

    return render_template("auth/signup.html", full_name="", email="", phone="")


def db_or(*conditions):
    from sqlalchemy import or_
    return or_(*conditions)


@auth_bp.post("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.landing"))