from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from models import AdminAccount, Attendance, Department, Employee, LeaveRequest, db


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        department = Department(department_name="Engineering")
        db.session.add(department)
        db.session.flush()
        db.session.add(AdminAccount(username="test-admin", full_name="Test Admin", password_hash=generate_password_hash("AdminPassword123")))
        employee = Employee(
            employee_code="EMP-001", full_name="Test Employee", email="employee@example.test",
            phone="", department_id=department.id, designation="Engineer", joining_date=date(2024, 1, 1),
            password_hash=generate_password_hash("EmployeePassword123"),
        )
        db.session.add(employee)
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login_admin(client):
    return client.post("/admin/login", data={"username": "test-admin", "password": "AdminPassword123"})


def test_role_separation_and_private_employee_routes(client):
    assert login_admin(client).status_code == 302
    assert client.get("/employee/").status_code == 403
    client.post("/logout")
    response = client.post("/employee/login", data={"identifier": "EMP-001", "password": "EmployeePassword123"})
    assert response.status_code == 302
    assert client.get("/admin/").status_code == 403
    assert client.get("/employee/").status_code == 200


def test_attendance_upsert_and_leave_approval(client, app):
    login_admin(client)
    with app.app_context():
        employee_id = Employee.query.filter_by(employee_code="EMP-001").one().id
    selected_date = date.today().isoformat()
    for status in ("Present", "Absent"):
        response = client.post("/admin/attendance", data={
            "date": selected_date,
            f"status_{employee_id}": status,
            f"remarks_{employee_id}": "test update",
        })
        assert response.status_code == 302
    with app.app_context():
        assert Attendance.query.filter_by(employee_id=employee_id, attendance_date=date.today()).count() == 1
        assert Attendance.query.filter_by(employee_id=employee_id, attendance_date=date.today()).one().status == "Absent"

    client.post("/logout")
    client.post("/employee/login", data={"identifier": "employee@example.test", "password": "EmployeePassword123"})
    start = date.today().replace(day=min(20, date.today().day))
    leave = client.post("/employee/leaves", data={
        "leave_type": "Personal", "start_date": start.isoformat(), "end_date": start.isoformat(), "reason": "Test request",
    })
    assert leave.status_code == 302
    client.post("/logout")
    login_admin(client)
    with app.app_context():
        leave_id = LeaveRequest.query.one().id
    decision = client.post("/admin/leaves", data={"leave_id": leave_id, "decision": "approved", "admin_remarks": "Approved"})
    assert decision.status_code == 302
    with app.app_context():
        assert db.session.get(LeaveRequest, leave_id).status == "approved"


def test_report_exports(client):
    login_admin(client)
    assert client.get("/admin/reports/export.csv").mimetype == "text/csv"
    assert client.get("/admin/reports/export.pdf").mimetype == "application/pdf"