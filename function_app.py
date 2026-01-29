import logging
import json
import os
import azure.functions as func
import pyodbc
from pydantic import BaseModel
from typing import Optional

# -------------------------
# Azure Function App
# -------------------------
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# -------------------------
# Data Model
# -------------------------
class Employee(BaseModel):
    id: Optional[int] = None
    name: str
    department: str
    salary: float

# -------------------------
# Database helper
# -------------------------
def get_db_connection():
    SERVER = os.getenv("SQL_SERVER")
    DATABASE = os.getenv("SQL_DATABASE")
    USERNAME = os.getenv("SQL_USERNAME")
    PASSWORD = os.getenv("SQL_PASSWORD")
    DRIVER = "{ODBC Driver 17 for SQL Server}"  # <- Azure Linux 支援 Driver 17

    if not all([SERVER, DATABASE, USERNAME, PASSWORD]):
        raise ValueError("Database configuration is incomplete")

    conn_str = (
        f"DRIVER={DRIVER};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={USERNAME};"
        f"PWD={PASSWORD};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=yes;"
        f"Connection Timeout=30;"
    )

    return pyodbc.connect(conn_str)

# -------------------------
# HTTP Trigger
# -------------------------
@app.route(
    route="employee",
    methods=["GET", "POST", "PUT", "DELETE"],
    auth_level=func.AuthLevel.ANONYMOUS
)
def employee_api(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Employee CRUD function triggered")

    # 建立 DB 連線
    try:
        conn = get_db_connection()
    except Exception as e:
        logging.exception("DB connection failed")
        return func.HttpResponse(
            json.dumps({"error": str(e), "type": type(e).__name__}),
            status_code=500,
            mimetype="application/json"
        )

    method = req.method

    try:
        body = req.get_json()
    except ValueError:
        body = {}

    # -------------------------
    # CREATE (POST)
    # -------------------------
    if method == "POST":
        try:
            emp = Employee(**body)
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO Employees (name, department, salary) VALUES (?, ?, ?)",
                    emp.name, emp.department, emp.salary
                )
                conn.commit()
            return func.HttpResponse(
                json.dumps({"message": "Employee created successfully"}),
                status_code=201,
                mimetype="application/json"
            )
        except Exception as e:
            logging.exception("POST failed")
            return func.HttpResponse(
                json.dumps({"error": str(e)}),
                status_code=400,
                mimetype="application/json"
            )

    # -------------------------
    # READ (GET)
    # -------------------------
    if method == "GET":
        emp_id = req.params.get("id")
        try:
            with conn.cursor() as cursor:
                if emp_id:
                    cursor.execute("SELECT * FROM Employees WHERE id = ?", emp_id)
                    row = cursor.fetchone()
                    if not row:
                        return func.HttpResponse("Employee not found", status_code=404)
                    employee = {
                        "id": row.id,
                        "name": row.name,
                        "department": row.department,
                        "salary": row.salary
                    }
                    return func.HttpResponse(json.dumps(employee), mimetype="application/json")
                else:
                    cursor.execute("SELECT * FROM Employees")
                    rows = cursor.fetchall()
                    employees = [
                        {"id": r.id, "name": r.name, "department": r.department, "salary": r.salary}
                        for r in rows
                    ]
                    return func.HttpResponse(json.dumps(employees), mimetype="application/json")
        except Exception as e:
            logging.exception("GET failed")
            return func.HttpResponse(
                json.dumps({"error": str(e)}),
                status_code=500,
                mimetype="application/json"
            )

    # -------------------------
    # UPDATE (PUT)
    # -------------------------
    if method == "PUT":
        try:
            emp = Employee(**body)
            if emp.id is None:
                return func.HttpResponse("Employee id is required", status_code=400)
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE Employees SET name=?, department=?, salary=? WHERE id=?",
                    emp.name, emp.department, emp.salary, emp.id
                )
                conn.commit()
            return func.HttpResponse(
                json.dumps({"message": "Employee updated successfully"}),
                mimetype="application/json"
            )
        except Exception as e:
            logging.exception("PUT failed")
            return func.HttpResponse(
                json.dumps({"error": str(e)}),
                status_code=400,
                mimetype="application/json"
            )

    # -------------------------
    # DELETE (DELETE)
    # -------------------------
    if method == "DELETE":
        emp_id = req.params.get("id")
        if not emp_id:
            return func.HttpResponse("Employee id is required", status_code=400)
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM Employees WHERE id = ?", emp_id)
                conn.commit()
            return func.HttpResponse(
                json.dumps({"message": f"Employee {emp_id} deleted successfully"}),
                mimetype="application/json"
            )
        except Exception as e:
            logging.exception("DELETE failed")
            return func.HttpResponse(
                json.dumps({"error": str(e)}),
                status_code=500,
                mimetype="application/json"
            )

    return func.HttpResponse("Method not allowed", status_code=405)
