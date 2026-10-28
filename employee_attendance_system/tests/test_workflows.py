from datetime import date

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from models import (
    AdminAccount,
    Attendance,
    AttendanceCorrectionRequest,
    Department,
    Employee,
    LeaveRequest,
    Notification,
    db,
)


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


def test_admin_and_employee_have_separate_login_pages(client):
    admin_login = client.get("/admin/login")
    employee_login = client.get("/employee/login")

    assert admin_login.status_code == 200
    assert b"Admin sign in" in admin_login.data
    assert b"auth-layout--admin" in admin_login.data
    assert b'name="username"' in admin_login.data
    assert b'name="identifier"' not in admin_login.data
    assert employee_login.status_code == 200
    assert b"Employee sign in" in employee_login.data
    assert b"auth-layout--employee" in employee_login.data
    assert b'name="identifier"' in employee_login.data
    assert b'name="username"' not in employee_login.data


def test_employee_can_self_register_but_cannot_access_admin(client, app):
    signup_page = client.get("/employee/signup")
    assert signup_page.status_code == 200
    assert b"Create an account" in signup_page.data

    response = client.post("/employee/signup", data={
        "full_name": "New Employee",
        "email": "new.employee@example.com",
        "phone": "555-0100",
        "password": "NewEmployeePassword123",
        "confirm_password": "NewEmployeePassword123",
    })
    assert response.status_code == 302
    assert "/employee/" in response.headers["Location"]
    assert client.get("/employee/").status_code == 200
    assert client.get("/admin/").status_code == 403

    with app.app_context():
        employee = Employee.query.filter_by(email="new.employee@example.com").one()
        assert employee.employee_code.startswith("NEW-")
        assert employee.department.department_name == "Unassigned"
        assert check_password_hash(employee.password_hash, "NewEmployeePassword123")


def test_self_registration_requires_a_strong_matching_password(client, app):
    response = client.post("/employee/signup", data={
        "full_name": "New Employee",
        "email": "new.employee@example.com",
        "password": "short",
        "confirm_password": "different",
    })
    assert response.status_code == 200
    assert b"at least 12 characters" in response.data
    with app.app_context():
        assert Employee.query.filter_by(email="new.employee@example.com").count() == 0


def test_admin_can_edit_reset_and_delete_employee_account(client, app):
    login_admin(client)
    with app.app_context():
        employee = Employee.query.filter_by(employee_code="EMP-001").one()
        employee_id = employee.id

    listing = client.get("/admin/employees")
    assert b"employee@example.test" in listing.data
    assert b"EMP-001" in listing.data
    assert b"password_hash" not in listing.data

    edit_response = client.post(f"/admin/employees/{employee_id}/edit", data={
        "full_name": "Updated Employee",
        "email": "updated.employee@example.test",
        "employee_code": "EMP-UPDATED",
        "phone": "555-0101",
        "designation": "Senior Engineer",
        "department_id": "1",
        "joining_date": "2024-01-01",
    })
    assert edit_response.status_code == 302

    reset_response = client.post(f"/admin/employees/{employee_id}/reset-password", data={
        "password": "ResetEmployeePassword123",
    })
    assert reset_response.status_code == 302

    with app.app_context():
        employee = db.session.get(Employee, employee_id)
        assert employee.email == "updated.employee@example.test"
        assert employee.employee_code == "EMP-UPDATED"
        assert check_password_hash(employee.password_hash, "ResetEmployeePassword123")
        db.session.add_all([
            Attendance(employee_id=employee_id, attendance_date=date.today(), status="Present"),
            LeaveRequest(employee_id=employee_id, leave_type="Personal", start_date=date.today(),
                         end_date=date.today(), reason="Test leave"),
            Notification(employee_id=employee_id, message="Test notification"),
            AttendanceCorrectionRequest(employee_id=employee_id, attendance_date=date.today(),
                                        requested_status="Absent", reason="Test correction"),
        ])
        db.session.commit()

    delete_response = client.post(f"/admin/employees/{employee_id}/delete")
    assert delete_response.status_code == 302
    with app.app_context():
        assert db.session.get(Employee, employee_id) is None
        assert Attendance.query.filter_by(employee_id=employee_id).count() == 0
        assert LeaveRequest.query.filter_by(employee_id=employee_id).count() == 0
        assert Notification.query.filter_by(employee_id=employee_id).count() == 0
        assert AttendanceCorrectionRequest.query.filter_by(employee_id=employee_id).count() == 0


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