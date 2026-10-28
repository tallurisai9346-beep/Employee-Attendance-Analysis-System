from datetime import date, timedelta

import numpy as np
import pandas as pd

from models import Attendance, Department, Employee, Holiday, LeaveRequest


def eligible_workdays(employee_id, start_date, end_date):
    if end_date < start_date:
        return 0
    weekdays = int(np.busday_count(start_date.isoformat(), (end_date + timedelta(days=1)).isoformat()))
    excluded = {holiday.holiday_date for holiday in Holiday.query.filter(Holiday.holiday_date.between(start_date, end_date)).all()}
    approved = LeaveRequest.query.filter_by(employee_id=employee_id, status="approved").filter(
        LeaveRequest.start_date <= end_date, LeaveRequest.end_date >= start_date
    ).all()
    for leave in approved:
        current = max(start_date, leave.start_date)
        last = min(end_date, leave.end_date)
        while current <= last:
            if current.weekday() < 5:
                excluded.add(current)
            current += timedelta(days=1)
    return max(0, weekdays - sum(day.weekday() < 5 for day in excluded))


def employee_summary(employee_id, start_date, end_date):
    records = Attendance.query.filter_by(employee_id=employee_id).filter(
        Attendance.attendance_date.between(start_date, end_date)
    ).all()
    excluded = {holiday.holiday_date for holiday in Holiday.query.filter(Holiday.holiday_date.between(start_date, end_date)).all()}
    approved = LeaveRequest.query.filter_by(employee_id=employee_id, status="approved").filter(
        LeaveRequest.start_date <= end_date, LeaveRequest.end_date >= start_date
    ).all()
    for leave in approved:
        current = max(start_date, leave.start_date)
        last = min(end_date, leave.end_date)
        while current <= last:
            if current.weekday() < 5:
                excluded.add(current)
            current += timedelta(days=1)
    counts = {"Present": 0, "Absent": 0, "Leave": 0, "Holiday": 0}
    for record in records:
        if record.status in ("Present", "Absent") and (record.attendance_date.weekday() >= 5 or record.attendance_date in excluded):
            continue
        counts[record.status] = counts.get(record.status, 0) + 1
    eligible = eligible_workdays(employee_id, start_date, end_date)
    counts["eligible"] = eligible
    counts["attendance_percentage"] = round(counts["Present"] / eligible * 100, 1) if eligible else 0
    counts["absenteeism_percentage"] = round(counts["Absent"] / eligible * 100, 1) if eligible else 0
    return counts


def team_eligible_workdays(employees, start_date, end_date):
    return sum(eligible_workdays(employee.id, start_date, end_date) for employee in employees)


def attendance_frame(start_date=None, end_date=None, employee_id=None, department_id=None):
    query = Attendance.query.join(Employee).join(Department)
    if start_date:
        query = query.filter(Attendance.attendance_date >= start_date)
    if end_date:
        query = query.filter(Attendance.attendance_date <= end_date)
    if employee_id:
        query = query.filter(Attendance.employee_id == employee_id)
    if department_id:
        query = query.filter(Employee.department_id == department_id)
    records = query.order_by(Attendance.attendance_date.desc()).all()
    return pd.DataFrame([
        {
            "date": row.attendance_date.isoformat(),
            "employee_code": row.employee.employee_code,
            "employee": row.employee.full_name,
            "department": row.employee.department.department_name,
            "status": row.status,
            "remarks": row.remarks,
        }
        for row in records
    ], columns=["date", "employee_code", "employee", "department", "status", "remarks"])


def monthly_counts(employee_id, year=None):
    year = year or date.today().year
    rows = Attendance.query.filter_by(employee_id=employee_id).filter(
        Attendance.attendance_date >= date(year, 1, 1),
        Attendance.attendance_date <= date(year, 12, 31),
    ).all()
    frame = pd.DataFrame([{"month": row.attendance_date.month, "status": row.status} for row in rows])
    if frame.empty:
        return {"labels": [], "present": [], "absent": []}
    grouped = frame.groupby(["month", "status"]).size().unstack(fill_value=0)
    months = list(range(1, 13))
    return {
        "labels": [date(year, month, 1).strftime("%b") for month in months],
        "present": [int(grouped.loc[month, "Present"]) if month in grouped.index and "Present" in grouped else 0 for month in months],
        "absent": [int(grouped.loc[month, "Absent"]) if month in grouped.index and "Absent" in grouped else 0 for month in months],
    }