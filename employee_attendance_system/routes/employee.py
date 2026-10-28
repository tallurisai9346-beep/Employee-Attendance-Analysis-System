import csv
import io
from datetime import date, timedelta

from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from models import (Attendance, AttendanceCorrectionRequest, Employee, LeaveRequest,
                    Notification, db)
from services.attendance import employee_summary, monthly_counts
from services.security import employee_required


employee_bp = Blueprint("employee", __name__)
PERSONAL_STATUSES = ("Present", "Absent", "Leave", "Holiday")


def current_employee():
    employee = db.session.get(Employee, session.get("employee_id"))
    if not employee or employee.account_status != "active":
        session.clear()
        abort(403)
    return employee


@employee_bp.get("/")
@employee_required
def dashboard():
    employee = current_employee()
    today = date.today()
    month_start = today.replace(day=1)
    summary = employee_summary(employee.id, month_start, today)
    records = Attendance.query.filter_by(employee_id=employee.id).order_by(Attendance.attendance_date.desc()).limit(8).all()
    notifications = Notification.query.filter_by(employee_id=employee.id, is_read=False).order_by(Notification.created_at.desc()).limit(8).all()
    return render_template("employee/dashboard.html", employee=employee, summary=summary,
                           records=records, notifications=notifications,
                           chart=monthly_counts(employee.id, today.year))


@employee_bp.route("/attendance", methods=["GET", "POST"])
@employee_required
def attendance():
    employee = current_employee()
    if request.method == "POST":
        try:
            requested_date = date.fromisoformat(request.form.get("attendance_date", ""))
            requested_status = request.form.get("requested_status")
            reason = request.form.get("reason", "").strip()
            if requested_status not in PERSONAL_STATUSES or not reason:
                raise ValueError
            db.session.add(AttendanceCorrectionRequest(employee_id=employee.id, attendance_date=requested_date,
                                                       requested_status=requested_status, reason=reason))
            db.session.commit()
            flash("Correction request sent to an administrator.", "success")
            return redirect(url_for("employee.attendance"))
        except ValueError:
            db.session.rollback()
            flash("Enter a valid date, status, and reason.", "danger")
    start_text = request.args.get("from", (date.today() - timedelta(days=30)).isoformat())
    end_text = request.args.get("to", date.today().isoformat())
    try:
        start_date, end_date = date.fromisoformat(start_text), date.fromisoformat(end_text)
    except ValueError:
        start_date, end_date = date.today() - timedelta(days=30), date.today()
    records = Attendance.query.filter_by(employee_id=employee.id).filter(
        Attendance.attendance_date.between(start_date, end_date)
    ).order_by(Attendance.attendance_date.desc()).all()
    summary = employee_summary(employee.id, start_date, end_date)
    return render_template("employee/attendance.html", employee=employee, records=records,
                           start_date=start_date, end_date=end_date, summary=summary)


@employee_bp.get("/attendance.csv")
@employee_required
def attendance_csv():
    employee = current_employee()
    records = Attendance.query.filter_by(employee_id=employee.id).order_by(Attendance.attendance_date.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "status", "remarks"])
    for record in records:
        writer.writerow([record.attendance_date.isoformat(), record.status, record.remarks])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=my-attendance.csv"
    return response


@employee_bp.route("/leaves", methods=["GET", "POST"])
@employee_required
def leaves():
    employee = current_employee()
    if request.method == "POST":
        try:
            start_date = date.fromisoformat(request.form.get("start_date", ""))
            end_date = date.fromisoformat(request.form.get("end_date", ""))
            leave_type = request.form.get("leave_type", "").strip()
            reason = request.form.get("reason", "").strip()
            if end_date < start_date or not leave_type or not reason:
                raise ValueError
            db.session.add(LeaveRequest(employee_id=employee.id, leave_type=leave_type,
                                        start_date=start_date, end_date=end_date, reason=reason))
            db.session.commit()
            flash("Leave request submitted for approval.", "success")
            return redirect(url_for("employee.leaves"))
        except ValueError:
            db.session.rollback()
            flash("Check the leave dates, type, and reason.", "danger")
    requests = LeaveRequest.query.filter_by(employee_id=employee.id).order_by(LeaveRequest.created_at.desc()).all()
    return render_template("employee/leaves.html", employee=employee, requests=requests)


@employee_bp.post("/leaves/<int:leave_id>/cancel")
@employee_required
def cancel_leave(leave_id):
    employee = current_employee()
    leave = LeaveRequest.query.filter_by(id=leave_id, employee_id=employee.id).first_or_404()
    if leave.status != "pending":
        abort(400)
    leave.status = "cancelled"
    db.session.commit()
    flash("Pending leave request cancelled.", "success")
    return redirect(url_for("employee.leaves"))


@employee_bp.route("/profile", methods=["GET", "POST"])
@employee_required
def profile():
    employee = current_employee()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "contact":
            employee.phone = request.form.get("phone", "").strip()
            db.session.commit()
            flash("Contact details updated.", "success")
        elif action == "password":
            old = request.form.get("current_password", "")
            new = request.form.get("new_password", "")
            if not check_password_hash(employee.password_hash, old):
                flash("Current password is incorrect.", "danger")
            elif len(new) < 12 or new != request.form.get("confirm_password"):
                flash("Passwords must match and contain at least 12 characters.", "danger")
            else:
                employee.password_hash = generate_password_hash(new)
                db.session.commit()
                flash("Password updated.", "success")
        return redirect(url_for("employee.profile"))
    return render_template("employee/profile.html", employee=employee)


@employee_bp.post("/notifications/<int:notification_id>/read")
@employee_required
def mark_notification_read(notification_id):
    employee = current_employee()
    notification = Notification.query.filter_by(id=notification_id, employee_id=employee.id).first_or_404()
    notification.is_read = True
    db.session.commit()
    return redirect(url_for("employee.dashboard"))