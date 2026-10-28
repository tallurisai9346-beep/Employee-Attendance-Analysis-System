# Employee Attendance Analysis System

A Flask application with a shared SQLite database and separate Admin and Employee workspaces. The app includes employee account management, attendance, leave and correction workflows, notifications, analytics, and CSV/PDF reports.

## Requirements

- Python 3.11 or newer
- A virtual environment
- SQLite for local development, or MySQL with a `DATABASE_URL` connection string

## Install and run on Windows PowerShell

From this directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
$env:ADMIN_USERNAME = "sai499"
$env:ADMIN_PASSWORD = Read-Host "Enter the admin password"
flask --app app set-admin-credentials
flask --app app run --debug --port 5001
```

The password is read into the shell environment, validated for 12 or more characters, and stored only as a Werkzeug password hash. Do not put it in source control or README files. The app creates `instance/database.db` automatically and seeds sample departments, employees, attendance history, and one pending leave request. On first initialization it prints a temporary sample employee password once; each sample account uses that same generated password. An administrator can reset an employee password later.

Open `http://127.0.0.1:5001/`. Admins use the Admin portal. Employees sign in with their registered email or employee code and the password provided by the administrator. The Admin creates employee accounts under **Employees**.

## MySQL

Install the included PyMySQL driver and set a SQLAlchemy URL before launch:

```powershell
$env:DATABASE_URL = "mysql+pymysql://user:password@localhost/attendance"
```

Create the database and grant the app user appropriate privileges before running the app. SQLite remains the default.

## Workflows

- Admin: manage employee records and logins, deactivate accounts, reset passwords, mark/update daily attendance, review leave and correction requests, manage departments and holidays, send announcements, and view activity logs.
- Employee: view only their own profile and attendance, filter personal history, export a CSV, request attendance corrections, request/cancel pending leave, read notifications, update phone, and change password.
- Reports: Admin exports the selected date range to CSV or PDF and reviews department and monthly breakdowns.
- Attendance policy: weekdays are eligible working days. Configured holidays and approved leave weekdays are excluded. Present percentage is present days divided by eligible days. Absenteeism percentage is absent days divided by eligible days. Unrecorded days never count as present.

## Security and deployment

- All account passwords use Werkzeug's `scrypt` password hash; plaintext is never stored.
- Admin and Employee routes check the authenticated role server-side. Employee queries are scoped to the current employee ID.
- State-changing forms use Flask-WTF CSRF tokens. Logout uses POST.
- Session cookies are HTTP-only and same-site, with a 30-minute inactivity timeout. Use HTTPS and set `COOKIE_SECURE=1` in production.
- Provide a stable random `SECRET_KEY` from a secret manager. Set `FLASK_DEBUG=0` and use a production WSGI server such as Gunicorn behind a TLS-terminating reverse proxy.
- Configure backups, database permissions, log retention, and a real SMTP/provider integration before production. Public employee self-registration is intentionally disabled; an Admin provisions accounts.
- Bootstrap, Bootstrap Icons, Google Fonts, and Plotly.js are loaded from CDNs; self-host these assets where policy or network availability requires it.

Run the workflow tests with:

```powershell
pytest
```