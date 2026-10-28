from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from models import AdminAccount, Employee


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


def db_or(*conditions):
    from sqlalchemy import or_
    return or_(*conditions)


@auth_bp.post("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.landing"))