import io
from datetime import date, datetime, timedelta

import pandas as pd
from flask import Blueprint, abort, flash, make_response, redirect, render_template, request, session, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from models import (ActivityLog, AdminAccount, Attendance, AttendanceCorrectionRequest, Department,
                    Employee, Holiday, LeaveRequest, Notification, db)
from services.activity import log_activity
from services.attendance import attendance_frame, employee_summary, team_eligible_workdays
from services.security import admin_required


admin_bp = Blueprint("admin", __name__)
ATTENDANCE_STATUSES = ("Present", "Absent", "Leave", "Holiday")


@admin_bp.get("/")
@admin_required
def dashboard():
    today = date.today()
    employees = Employee.query.filter_by(account_status="active").all()
    today_rows = Attendance.query.join(Employee).filter(
        Attendance.attendance_date == today, Employee.account_status == "active"
    ).all()
    counts = {status: sum(row.status == status for row in today_rows) for status in ATTENDANCE_STATUSES}
    month_start = today.replace(day=1)
    present_month = sum(employee_summary(employee.id, month_start, today)["Present"] for employee in employees)
    eligible = max(team_eligible_workdays(employees, month_start, today), 1)
    attendance_percent = round(present_month / eligible * 100, 1)
    department_rows = [
        (name, count)
        for name, count in db.session.query(Department.department_name, func.count(Employee.id)).join(Employee).filter(
            Employee.account_status == "active"
        ).group_by(Department.id).all()
    ]
    recent = Attendance.query.order_by(Attendance.attendance_date.desc(), Attendance.updated_at.desc()).limit(8).all()
    pending_leaves = LeaveRequest.query.filter_by(status="pending").count()
    months = pd.date_range(end=today.replace(day=1), periods=6, freq="MS")
    trend = []
    for month in months:
        next_month = month.date().replace(day=28) + timedelta(days=4)
        month_end = next_month - timedelta(days=next_month.day)
        trend.append({
            "label": month.strftime("%b"),
            "present": Attendance.query.filter(Attendance.attendance_date.between(month.date(), month_end), Attendance.status == "Present").count(),
            "absent": Attendance.query.filter(Attendance.attendance_date.between(month.date(), month_end), Attendance.status == "Absent").count(),
        })
    return render_template("admin/dashboard.html", total=len(employees), counts=counts,
                           attendance_percent=attendance_percent, departments=department_rows,
                           recent=recent, pending_leaves=pending_leaves, trend=trend)


@admin_bp.route("/employees", methods=["GET", "POST"])
@admin_required
def employees():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        code = request.form.get("employee_code", "").strip().upper()
        password = request.form.get("password", "")
        try:
            joining_date = date.fromisoformat(request.form.get("joining_date", ""))
            department_id = int(request.form.get("department_id", ""))
            department = db.session.get(Department, department_id)
            if not all((full_name, email, code, department)) or len(password) < 12:
                raise ValueError("Complete all required fields and use a password with at least 12 characters.")
            employee = Employee(
                full_name=full_name, email=email, employee_code=code,
                phone=request.form.get("phone", "").strip(), department_id=department_id,
                designation=request.form.get("designation", "").strip(), joining_date=joining_date,
                password_hash=generate_password_hash(password),
            )
            db.session.add(employee)
            log_activity("employee_created", f"{code} {full_name}")
            db.session.commit()
            flash("Employee account created.", "success")
            return redirect(url_for("admin.employees"))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
        except Exception:
            db.session.rollback()
            flash("Employee code or email is already in use.", "danger")
    query = Employee.query.join(Department)
    search = request.args.get("q", "").strip()
    department_id = request.args.get("department", "")
    status = request.args.get("status", "")
    if search:
        query = query.filter(or_(Employee.full_name.ilike(f"%{search}%"), Employee.email.ilike(f"%{search}%"), Employee.employee_code.ilike(f"%{search}%")))
    if department_id.isdigit():
        query = query.filter(Employee.department_id == int(department_id))
    if status in ("active", "inactive"):
        query = query.filter(Employee.account_status == status)
    return render_template("admin/employees.html", employees=query.order_by(Employee.full_name).all(),
                           departments=Department.query.order_by(Department.department_name).all(), q=search,
                           department_id=department_id, status=status)


@admin_bp.post("/employees/<int:employee_id>/edit")
@admin_required
def edit_employee(employee_id):
    employee = db.get_or_404(Employee, employee_id)
    try:
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        employee_code = request.form.get("employee_code", "").strip().upper()
        phone = request.form.get("phone", "").strip()
        designation = request.form.get("designation", "").strip()
        department_id = int(request.form.get("department_id", ""))
        joining_date = date.fromisoformat(request.form.get("joining_date", ""))
        department = db.session.get(Department, department_id)
        if not full_name or len(full_name) > 100 or not email or len(email) > 254:
            raise ValueError("Enter a valid name and email address.")
        if not employee_code or len(employee_code) > 30 or len(phone) > 30 or len(designation) > 100:
            raise ValueError("Check the employee code, phone, and designation fields.")
        if department is None:
            raise ValueError("Choose a valid department.")
        if Employee.query.filter(Employee.id != employee.id, Employee.email == email).first():
            raise ValueError("That email address is already assigned to another account.")
        if Employee.query.filter(Employee.id != employee.id, Employee.employee_code == employee_code).first():
            raise ValueError("That employee code is already assigned to another account.")
        employee.full_name = full_name
        employee.email = email
        employee.employee_code = employee_code
        employee.phone = phone
        employee.designation = designation
        employee.department_id = department.id
        employee.joining_date = joining_date
        log_activity("employee_updated", employee.employee_code)
        db.session.commit()
        flash("Employee profile updated.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    except IntegrityError:
        db.session.rollback()
        flash("That email or employee code is already assigned to another account.", "danger")
    return redirect(url_for("admin.employees"))


@admin_bp.post("/employees/<int:employee_id>/status")
@admin_required
def employee_status(employee_id):
    employee = db.get_or_404(Employee, employee_id)
    employee.account_status = "inactive" if employee.account_status == "active" else "active"
    log_activity("employee_status_changed", f"{employee.employee_code}: {employee.account_status}")
    db.session.commit()
    flash("Employee account status updated.", "success")
    return redirect(url_for("admin.employees"))


@admin_bp.post("/employees/<int:employee_id>/reset-password")
@admin_required
def reset_employee_password(employee_id):
    employee = db.get_or_404(Employee, employee_id)
    password = request.form.get("password", "")
    if len(password) < 12:
        flash("The new password must contain at least 12 characters.", "danger")
    else:
        employee.password_hash = generate_password_hash(password)
        log_activity("employee_password_reset", employee.employee_code)
        db.session.commit()
        flash("Employee password reset. The old password can no longer be viewed or used.", "success")
    return redirect(url_for("admin.employees"))


@admin_bp.post("/employees/<int:employee_id>/delete")
@admin_required
def delete_employee(employee_id):
    employee = db.get_or_404(Employee, employee_id)
    employee_label = f"{employee.employee_code} {employee.email}"
    log_activity("employee_account_deleted", employee_label)
    db.session.delete(employee)
    db.session.commit()
    flash("Employee account and its associated attendance, leave, correction, and notification records were deleted.", "success")
    return redirect(url_for("admin.employees"))


@admin_bp.route("/attendance", methods=["GET", "POST"])
@admin_required
def attendance():
    selected_date = date.fromisoformat(request.values.get("date", date.today().isoformat()))
    employees = Employee.query.filter_by(account_status="active").order_by(Employee.full_name).all()
    if request.method == "POST":
        for employee in employees:
            status = request.form.get(f"status_{employee.id}")
            if status not in ATTENDANCE_STATUSES:
                continue
            record = Attendance.query.filter_by(employee_id=employee.id, attendance_date=selected_date).first()
            if record:
                record.status = status
                record.remarks = request.form.get(f"remarks_{employee.id}", "").strip()
            else:
                db.session.add(Attendance(employee_id=employee.id, attendance_date=selected_date,
                                          status=status, remarks=request.form.get(f"remarks_{employee.id}", "").strip()))
        log_activity("attendance_saved", selected_date.isoformat())
        db.session.commit()
        flash("Attendance saved. Existing records were updated without creating duplicates.", "success")
        return redirect(url_for("admin.attendance", date=selected_date.isoformat()))
    existing = {row.employee_id: row for row in Attendance.query.filter_by(attendance_date=selected_date).all()}
    return render_template("admin/attendance.html", employees=employees, selected_date=selected_date, existing=existing)


@admin_bp.route("/leaves", methods=["GET", "POST"])
@admin_required
def leaves():
    if request.method == "POST":
        leave = db.get_or_404(LeaveRequest, request.form.get("leave_id", type=int))
        decision = request.form.get("decision")
        if decision not in ("approved", "rejected") or leave.status != "pending":
            abort(400)
        leave.status = decision
        leave.admin_remarks = request.form.get("admin_remarks", "").strip()
        db.session.add(Notification(employee_id=leave.employee_id, message=f"Your {leave.leave_type} leave request was {decision}."))
        log_activity("leave_decided", f"Leave {leave.id}: {decision}")
        db.session.commit()
        flash(f"Leave request {decision}.", "success")
        return redirect(url_for("admin.leaves"))
    requests = LeaveRequest.query.join(Employee).order_by(LeaveRequest.created_at.desc()).all()
    return render_template("admin/leaves.html", requests=requests)


@admin_bp.route("/corrections", methods=["GET", "POST"])
@admin_required
def corrections():
    if request.method == "POST":
        item = db.get_or_404(AttendanceCorrectionRequest, request.form.get("request_id", type=int))
        decision = request.form.get("decision")
        if decision not in ("approved", "rejected") or item.status != "pending":
            abort(400)
        item.status = decision
        item.admin_remarks = request.form.get("admin_remarks", "").strip()
        if decision == "approved":
            record = Attendance.query.filter_by(employee_id=item.employee_id, attendance_date=item.attendance_date).first()
            if record:
                record.status = item.requested_status
                record.remarks = item.reason
            else:
                db.session.add(Attendance(employee_id=item.employee_id, attendance_date=item.attendance_date,
                                          status=item.requested_status, remarks=item.reason))
        db.session.add(Notification(employee_id=item.employee_id, message=f"Your attendance correction for {item.attendance_date} was {decision}."))
        log_activity("correction_decided", f"Request {item.id}: {decision}")
        db.session.commit()
        flash("Correction request updated.", "success")
        return redirect(url_for("admin.corrections"))
    requests = AttendanceCorrectionRequest.query.join(Employee).order_by(AttendanceCorrectionRequest.created_at.desc()).all()
    return render_template("admin/corrections.html", requests=requests)


@admin_bp.get("/reports")
@admin_required
def reports():
    end_date = date.fromisoformat(request.args.get("to", date.today().isoformat()))
    start_date = date.fromisoformat(request.args.get("from", (end_date.replace(day=1)).isoformat()))
    employee_id = request.args.get("employee_id", type=int)
    department_id = request.args.get("department_id", type=int)
    frame = attendance_frame(start_date, end_date, employee_id, department_id)
    active_query = Employee.query.filter_by(account_status="active")
    if employee_id:
        active_query = active_query.filter(Employee.id == employee_id)
    if department_id:
        active_query = active_query.filter(Employee.department_id == department_id)
    active_employees = active_query.all()
    summary = {status: 0 for status in ATTENDANCE_STATUSES}
    for employee in active_employees:
        employee_counts = employee_summary(employee.id, start_date, end_date)
        for status in ATTENDANCE_STATUSES:
            summary[status] += employee_counts[status]
    employee_breakdown = {}
    if not frame.empty:
        grouped_employees = frame.groupby(["employee_code", "employee", "department", "status"]).size().unstack(fill_value=0)
        for employee_code, employee_name, department_name in grouped_employees.index:
            rows = grouped_employees.loc[(employee_code, employee_name, department_name)]
            employee_breakdown[f"{employee_name} · {employee_code}"] = {
                "department": department_name,
                **{status: int(rows[status]) if status in rows.index else 0 for status in ATTENDANCE_STATUSES},
            }
    eligible_days = team_eligible_workdays(active_employees, start_date, end_date)
    attendance_percent = round(summary.get("Present", 0) / eligible_days * 100, 1) if eligible_days else 0
    absenteeism_percent = round(summary.get("Absent", 0) / eligible_days * 100, 1) if eligible_days else 0
    departments = frame.groupby(["department", "status"]).size().unstack(fill_value=0).to_dict(orient="index") if not frame.empty else {}
    trend = []
    if not frame.empty:
        frame["month"] = pd.to_datetime(frame["date"]).dt.to_period("M")
        monthly = frame.groupby(["month", "status"]).size().unstack(fill_value=0)
        trend = [{
            "label": month.strftime("%b %Y"),
            **{status: int(monthly.loc[month, status]) if status in monthly else 0 for status in ATTENDANCE_STATUSES},
        } for month in monthly.index]
    return render_template("admin/reports.html", start_date=start_date, end_date=end_date,
                           summary=summary, departments=departments, trend=trend,
                           attendance_percent=attendance_percent, absenteeism_percent=absenteeism_percent,
                           employees=Employee.query.filter_by(account_status="active").order_by(Employee.full_name).all(),
                           departments_list=Department.query.order_by(Department.department_name).all(),
                           selected_employee=employee_id, selected_department=department_id,
                           employee_breakdown=employee_breakdown)


@admin_bp.get("/reports/export.csv")
@admin_required
def export_csv():
    end_date = date.fromisoformat(request.args.get("to", date.today().isoformat()))
    start_date = date.fromisoformat(request.args.get("from", end_date.replace(day=1).isoformat()))
    data = attendance_frame(start_date, end_date, request.args.get("employee_id", type=int),
                            request.args.get("department_id", type=int)).to_csv(index=False)
    response = make_response(data)
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=attendance-report.csv"
    return response


@admin_bp.get("/reports/export.pdf")
@admin_required
def export_pdf():
    end_date = date.fromisoformat(request.args.get("to", date.today().isoformat()))
    start_date = date.fromisoformat(request.args.get("from", end_date.replace(day=1).isoformat()))
    frame = attendance_frame(start_date, end_date, request.args.get("employee_id", type=int),
                             request.args.get("department_id", type=int))
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(letter), title="Attendance report")
    rows = [list(frame.columns)] + frame.astype(str).values.tolist()
    table = Table(rows or [["No attendance records"]], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20251f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d9dfd7")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f1")]),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
    ]))
    document.build([table])
    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=attendance-report.pdf"
    return response


@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "department":
            name = request.form.get("department_name", "").strip()
            if not name:
                flash("Department name is required.", "danger")
            elif Department.query.filter(func.lower(Department.department_name) == name.lower()).first():
                flash("That department already exists.", "danger")
            else:
                db.session.add(Department(department_name=name))
                log_activity("department_created", name)
                db.session.commit()
                flash("Department added.", "success")
        elif action == "holiday":
            try:
                holiday_date = date.fromisoformat(request.form.get("holiday_date", ""))
                name = request.form.get("holiday_name", "").strip()
                db.session.add(Holiday(holiday_date=holiday_date, name=name))
                log_activity("holiday_added", name)
                db.session.commit()
                flash("Holiday added.", "success")
            except Exception:
                db.session.rollback()
                flash("Enter a valid holiday name and date.", "danger")
        elif action == "password":
            admin = db.session.get(AdminAccount, session["admin_id"])
            new_password = request.form.get("new_password", "")
            if not admin or not check_password_hash(admin.password_hash, request.form.get("current_password", "")):
                flash("Current password is incorrect.", "danger")
            elif len(new_password) < 12 or new_password != request.form.get("confirm_password"):
                flash("Passwords must match and contain at least 12 characters.", "danger")
            else:
                admin.password_hash = generate_password_hash(new_password)
                log_activity("admin_password_changed")
                db.session.commit()
                flash("Admin password updated.", "success")
        elif action == "announcement":
            message = request.form.get("message", "").strip()
            if message:
                db.session.add_all([Notification(employee_id=row.id, message=message) for row in Employee.query.filter_by(account_status="active").all()])
                log_activity("announcement_sent", message[:100])
                db.session.commit()
                flash("Announcement sent to active employees.", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", departments=Department.query.order_by(Department.department_name).all(),
                           holidays=Holiday.query.order_by(Holiday.holiday_date.desc()).all(),
                           activities=ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(20).all())