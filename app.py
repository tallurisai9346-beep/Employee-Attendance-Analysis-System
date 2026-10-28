from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
import sqlite3, csv, io, os
from datetime import date, datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")
DB_PATH = os.path.join(os.path.dirname(__file__), "attendance.db")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'Admin'
        );
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            department TEXT NOT NULL,
            designation TEXT,
            join_date TEXT,
            status TEXT NOT NULL DEFAULT 'Active'
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Present','Absent','Late','Leave','Half Day')),
            check_in TEXT,
            check_out TEXT,
            notes TEXT,
            UNIQUE(employee_id, attendance_date),
            FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
        );
        """)
        if not con.execute("SELECT id FROM users WHERE username='admin'").fetchone():
            con.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)",
                        ("admin", "admin123", "Admin"))
        count = con.execute("SELECT COUNT(*) AS n FROM employees").fetchone()["n"]
        if count == 0:
            sample = [
                ("EMP001","Ravi Kumar","ravi@example.com","9876543210","IT","Software Developer","2025-06-10","Active"),
                ("EMP002","Priya Reddy","priya@example.com","9876543211","HR","HR Executive","2025-07-01","Active"),
                ("EMP003","Suresh Babu","suresh@example.com","9876543212","Finance","Accountant","2024-11-15","Active"),
                ("EMP004","Divya Sharma","divya@example.com","9876543213","Marketing","Marketing Associate","2026-01-08","Active"),
                ("EMP005","Kiran Rao","kiran@example.com","9876543214","IT","QA Engineer","2025-09-20","Inactive"),
            ]
            con.executemany("""INSERT INTO employees(employee_code,name,email,phone,department,designation,join_date,status)
                               VALUES(?,?,?,?,?,?,?,?)""", sample)

init_db()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE username=? AND password=?", (username,password)).fetchone()
        if user:
            session["user"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    today = request.args.get("date") or date.today().isoformat()
    with db() as con:
        total = con.execute("SELECT COUNT(*) n FROM employees WHERE status='Active'").fetchone()["n"]
        marked = con.execute("SELECT COUNT(*) n FROM attendance WHERE attendance_date=?", (today,)).fetchone()["n"]
        present = con.execute("SELECT COUNT(*) n FROM attendance WHERE attendance_date=? AND status IN ('Present','Late','Half Day')", (today,)).fetchone()["n"]
        absent = con.execute("SELECT COUNT(*) n FROM attendance WHERE attendance_date=? AND status='Absent'", (today,)).fetchone()["n"]
        leave = con.execute("SELECT COUNT(*) n FROM attendance WHERE attendance_date=? AND status='Leave'", (today,)).fetchone()["n"]
        dept = con.execute("""SELECT department, COUNT(*) total FROM employees WHERE status='Active'
                               GROUP BY department ORDER BY total DESC""").fetchall()
        recent = con.execute("""SELECT a.attendance_date,a.status,a.check_in,a.check_out,e.employee_code,e.name,e.department
                                FROM attendance a JOIN employees e ON e.id=a.employee_id
                                ORDER BY a.attendance_date DESC,a.id DESC LIMIT 8""").fetchall()
        employees = con.execute("SELECT id,employee_code,name,department FROM employees WHERE status='Active' ORDER BY name").fetchall()
    return render_template("dashboard.html", today=today, total=total, marked=marked, present=present,
                           absent=absent, leave=leave, dept=dept, recent=recent, employees=employees)

@app.route("/employees")
@login_required
def employees():
    q = request.args.get("q","").strip()
    department = request.args.get("department","")
    status = request.args.get("status","")
    sql = "SELECT * FROM employees WHERE 1=1"
    args = []
    if q:
        sql += " AND (name LIKE ? OR employee_code LIKE ? OR email LIKE ?)"
        args += [f"%{q}%"]*3
    if department:
        sql += " AND department=?"; args.append(department)
    if status:
        sql += " AND status=?"; args.append(status)
    sql += " ORDER BY id DESC"
    with db() as con:
        rows = con.execute(sql,args).fetchall()
        departments = [r["department"] for r in con.execute("SELECT DISTINCT department FROM employees ORDER BY department")]
    return render_template("employees.html", employees=rows, q=q, department=department, status=status, departments=departments)

@app.route("/employees/add", methods=["GET","POST"])
@app.route("/employees/<int:emp_id>/edit", methods=["GET","POST"])
@login_required
def employee_form(emp_id=None):
    employee = None
    with db() as con:
        if emp_id:
            employee = con.execute("SELECT * FROM employees WHERE id=?", (emp_id,)).fetchone()
            if not employee:
                flash("Employee not found.", "error")
                return redirect(url_for("employees"))
        if request.method == "POST":
            values = [request.form.get(k,"").strip() for k in
                      ["employee_code","name","email","phone","department","designation","join_date","status"]]
            if not values[0] or not values[1] or not values[4]:
                flash("Employee code, name, and department are required.", "error")
            else:
                try:
                    if emp_id:
                        con.execute("""UPDATE employees SET employee_code=?,name=?,email=?,phone=?,department=?,designation=?,join_date=?,status=? WHERE id=?""",
                                    (*values, emp_id))
                    else:
                        con.execute("""INSERT INTO employees(employee_code,name,email,phone,department,designation,join_date,status)
                                       VALUES(?,?,?,?,?,?,?,?)""", values)
                    con.commit()
                    flash("Employee saved successfully.", "success")
                    return redirect(url_for("employees"))
                except sqlite3.IntegrityError:
                    flash("Employee code already exists. Please use a unique code.", "error")
    return render_template("employee_form.html", employee=employee)

@app.route("/employees/<int:emp_id>/delete", methods=["POST"])
@login_required
def employee_delete(emp_id):
    with db() as con:
        con.execute("DELETE FROM employees WHERE id=?", (emp_id,))
    flash("Employee and associated attendance records deleted.", "success")
    return redirect(url_for("employees"))

@app.route("/attendance", methods=["GET","POST"])
@login_required
def attendance():
    selected_date = request.values.get("date") or date.today().isoformat()
    if request.method == "POST":
        ids = request.form.getlist("employee_id")
        with db() as con:
            for emp_id in ids:
                status = request.form.get(f"status_{emp_id}", "Present")
                check_in = request.form.get(f"in_{emp_id}","").strip()
                check_out = request.form.get(f"out_{emp_id}","").strip()
                notes = request.form.get(f"notes_{emp_id}","").strip()
                con.execute("""INSERT INTO attendance(employee_id,attendance_date,status,check_in,check_out,notes)
                               VALUES(?,?,?,?,?,?)
                               ON CONFLICT(employee_id,attendance_date) DO UPDATE SET
                               status=excluded.status,check_in=excluded.check_in,check_out=excluded.check_out,notes=excluded.notes""",
                            (emp_id, selected_date, status, check_in or None, check_out or None, notes or None))
        flash(f"Attendance saved for {selected_date}.", "success")
        return redirect(url_for("attendance", date=selected_date))
    with db() as con:
        rows = con.execute("""SELECT e.*,a.status AS attendance_status,a.check_in,a.check_out,a.notes
                              FROM employees e LEFT JOIN attendance a
                              ON e.id=a.employee_id AND a.attendance_date=?
                              WHERE e.status='Active' ORDER BY e.name""", (selected_date,)).fetchall()
    return render_template("attendance.html", rows=rows, selected_date=selected_date)

@app.route("/reports")
@login_required
def reports():
    start = request.args.get("start") or date.today().replace(day=1).isoformat()
    end = request.args.get("end") or date.today().isoformat()
    department = request.args.get("department","")
    with db() as con:
        sql = """SELECT e.id,e.employee_code,e.name,e.department,
                 SUM(CASE WHEN a.status IN ('Present','Late','Half Day') THEN 1 ELSE 0 END) present,
                 SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) absent,
                 SUM(CASE WHEN a.status='Leave' THEN 1 ELSE 0 END) leave_days,
                 COUNT(a.id) marked
                 FROM employees e LEFT JOIN attendance a ON e.id=a.employee_id AND a.attendance_date BETWEEN ? AND ?
                 WHERE 1=1"""
        args = [start,end]
        if department:
            sql += " AND e.department=?"; args.append(department)
        sql += " GROUP BY e.id ORDER BY e.name"
        rows = con.execute(sql,args).fetchall()
        departments = [r["department"] for r in con.execute("SELECT DISTINCT department FROM employees ORDER BY department")]
    results = []
    for r in rows:
        d = dict(r)
        d["present"] = d["present"] or 0
        d["absent"] = d["absent"] or 0
        d["leave_days"] = d["leave_days"] or 0
        d["marked"] = d["marked"] or 0
        d["percentage"] = round((d["present"] / d["marked"] * 100), 1) if d["marked"] else 0
        results.append(d)
    return render_template("reports.html", rows=results, start=start, end=end, department=department, departments=departments)

@app.route("/reports/export")
@login_required
def export_report():
    start = request.args.get("start") or date.today().replace(day=1).isoformat()
    end = request.args.get("end") or date.today().isoformat()
    department = request.args.get("department","")
    with db() as con:
        sql = """SELECT e.employee_code,e.name,e.department,
                 SUM(CASE WHEN a.status IN ('Present','Late','Half Day') THEN 1 ELSE 0 END) present,
                 SUM(CASE WHEN a.status='Absent' THEN 1 ELSE 0 END) absent,
                 SUM(CASE WHEN a.status='Leave' THEN 1 ELSE 0 END) leave_days,
                 COUNT(a.id) marked
                 FROM employees e LEFT JOIN attendance a ON e.id=a.employee_id AND a.attendance_date BETWEEN ? AND ?
                 WHERE 1=1"""
        args = [start,end]
        if department:
            sql += " AND e.department=?"; args.append(department)
        sql += " GROUP BY e.id ORDER BY e.name"
        rows = con.execute(sql,args).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee Code","Employee Name","Department","Present","Absent","Leave","Marked Days","Attendance %"])
    for r in rows:
        marked = r["marked"] or 0
        present = r["present"] or 0
        writer.writerow([r["employee_code"],r["name"],r["department"],present,r["absent"] or 0,r["leave_days"] or 0,marked,round(present/marked*100,1) if marked else 0])
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=attendance_report_{start}_to_{end}.csv"
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    return response

@app.route("/import", methods=["GET","POST"])
@login_required
def import_csv():
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename.lower().endswith(".csv"):
            flash("Please select a CSV file.", "error")
            return redirect(url_for("import_csv"))
        try:
            stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
            reader = csv.DictReader(stream)
            required = {"employee_code","name","department"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                flash("CSV must contain columns: employee_code, name, department. Optional: email, phone, designation, join_date, status.", "error")
                return redirect(url_for("import_csv"))
            inserted = 0
            with db() as con:
                for row in reader:
                    code = (row.get("employee_code") or "").strip()
                    name = (row.get("name") or "").strip()
                    dept = (row.get("department") or "").strip()
                    if not code or not name or not dept:
                        continue
                    con.execute("""INSERT INTO employees(employee_code,name,email,phone,department,designation,join_date,status)
                                   VALUES(?,?,?,?,?,?,?,?)
                                   ON CONFLICT(employee_code) DO UPDATE SET name=excluded.name,email=excluded.email,
                                   phone=excluded.phone,department=excluded.department,designation=excluded.designation,
                                   join_date=excluded.join_date,status=excluded.status""",
                                (code,name,row.get("email","").strip(),row.get("phone","").strip(),dept,
                                 row.get("designation","").strip(),row.get("join_date","").strip(),row.get("status","Active").strip() or "Active"))
                    inserted += 1
            flash(f"Imported or updated {inserted} employee records.", "success")
        except Exception as exc:
            flash(f"Could not import file: {exc}", "error")
        return redirect(url_for("employees"))
    return render_template("import.html")

@app.route("/settings", methods=["GET","POST"])
@login_required
def settings():
    if request.method == "POST":
        old = request.form.get("old_password","")
        new = request.form.get("new_password","")
        if len(new) < 8:
            flash("New password must contain at least 8 characters.", "error")
        else:
            with db() as con:
                user = con.execute("SELECT * FROM users WHERE username=?", (session["user"],)).fetchone()
                if user and user["password"] == old:
                    con.execute("UPDATE users SET password=? WHERE id=?", (new,user["id"]))
                    flash("Password updated. Please sign in again next time with the new password.", "success")
                else:
                    flash("Current password is incorrect.", "error")
    return render_template("settings.html")

if __name__ == "__main__":
    app.run(debug=True)
