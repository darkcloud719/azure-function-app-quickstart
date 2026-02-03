import logging
import json
import os
import azure.functions as func
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv
import urllib.parse

load_dotenv()

# -------------------------
# Azure Function App
# -------------------------
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# -------------------------
# Database Configuration
# -------------------------
AZURE_SQL_SERVER = os.getenv("AZURE_SQL_SERVER")
AZURE_SQL_DATABASE = os.getenv("AZURE_SQL_DATABASE")
AZURE_SQL_USERNAME = os.getenv("AZURE_SQL_USERNAME")
AZURE_SQL_PASSWORD = os.getenv("AZURE_SQL_PASSWORD")

# print(AZURE_SQL_SERVER, AZURE_SQL_DATABASE, AZURE_SQL_USERNAME, AZURE_SQL_PASSWORD)

if not all([
    AZURE_SQL_SERVER,
    AZURE_SQL_DATABASE,
    AZURE_SQL_USERNAME,
    AZURE_SQL_PASSWORD
]):
    raise ValueError("Database configuration is incomplete")

AZURE_SQL_PASSWORD = urllib.parse.quote_plus(AZURE_SQL_PASSWORD)
driver = "ODBC Driver 17 for SQL Server"

CONNECTION_STRING =  f"mssql+pyodbc://{AZURE_SQL_USERNAME}:{AZURE_SQL_PASSWORD}@{AZURE_SQL_SERVER}:1433/{AZURE_SQL_DATABASE}?driver={driver.replace(' ', '+')}&encrypt=yes&trustServerCertificate=yes"

# ----------------------------
# SQLAlchemy Setup
# ----------------------------
engine = create_engine(
    CONNECTION_STRING,
    pool_pre_ping=True,
    future=True
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)

Base = declarative_base()

# -------------------------
# ORM Model
# -------------------------
class EmployeeORM(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    department = Column(String(100), nullable=False)
    salary = Column(Float, nullable=False)

Base.metadata.create_all(bind=engine)

# -------------------------
# Pydantic Model
# -------------------------
class Employee(BaseModel):
    id: Optional[int] = None
    name: str
    department: str
    salary: float

    model_config = {
        "from_attributes": True
    }        

# ----------------------------
# Database Dependency
# ----------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------
# HTTP Trigger
# -------------------------
@app.route(
    route="TEST",
    methods=["GET", "POST", "PUT", "DELETE"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
@app.function_name(name="get_environment_variable")
def get_environment_variable(req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(json.dumps({"AZURE_SQL_SERVER": AZURE_SQL_SERVER, "AZURE_SQL_DATABASE": AZURE_SQL_DATABASE, "AZURE_SQL_USERNAME": AZURE_SQL_USERNAME, "AZURE_SQL_PASSWORD": AZURE_SQL_PASSWORD}), status_code=200, mimetype="application/json")

@app.route(
    route="employee",
    methods=["GET", "POST", "PUT", "DELETE"],
    auth_level=func.AuthLevel.ANONYMOUS
)
@app.function_name(name="employee_api")
def employee_api(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Employee CRUD function triggered")

    try:
        db: Session = next(get_db())
    except Exception as e:
        logging.error(f"Database connection error: {e}")
        return func.HttpResponse(
            json.dumps({"error": "Database connection error", "details": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
    
    method = req.method
    
    try:
        body = req.get_json()
    except ValueError:
        body = None

    # -------------------------
    # CREATE (POST)
    # -------------------------
    if method == "POST":
        try:
            # emp = Employee(**body)
            # new_emp = EmployeeORM(
            #     name=emp.name,
            #     department=emp.department,
            #     salary=emp.salary
            # )
            emp = Employee(**body)
            new_emp = EmployeeORM(**emp.dict())
            db.add(new_emp)
            db.commit()
            return func.HttpResponse(
                json.dumps({"message": "Employee created successfully"}),
                status_code=201,
                mimetype="application/json"
            )
        except Exception as e:
            db.rollback()
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
            if emp_id:
                employee = db.query(EmployeeORM).filter(EmployeeORM.id == emp_id).first()
                if not employee:
                    return func.HttpResponse(json.dumps({"error": "Employee not found"}), status_code=404, mimetype="application/json")
                return func.HttpResponse(
                    json.dumps(Employee.from_orm(employee).dict()),
                    mimetype="application/json"
                )
            employees = db.query(EmployeeORM).all()
            result = [Employee.from_orm(emp).dict() for emp in employees]

            return func.HttpResponse(
                json.dumps(result),
                mimetype="application/json"
            )
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
                return func.HttpResponse(
                    json.dumps({"error": "Employee id is required"}),
                    status_code=400,
                    mimetype="application/json"
                )
            
            employee = db.query(EmployeeORM).filter(EmployeeORM.id == emp.id).first()
            
            if not employee:
                return func.HttpResponse(
                    json.dumps({"error": "Employee not found"}),
                    status_code=404,
                    mimetype="application/json"
                )
            
            employee.name = emp.name
            employee.department = emp.department
            employee.salary = emp.salary
            db.commit()
            db.refresh(employee)
            return func.HttpResponse(
                json.dumps({"message": "Employee updated successfully"}),
                mimetype="application/json"
            )
        
        except Exception as e:
            db.rollback()
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
            return func.HttpResponse(
                json.dumps({"error": "Employee id is required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        try:
            employee = db.query(EmployeeORM).filter(
                EmployeeORM.id == emp_id
            ).first()

            if not employee:
                return func.HttpResponse(
                    json.dumps({"error": "Employee not found"}),
                    status_code=404,
                    miimetype="application/json"
                )
            
            db.delete(employee)
            db.commit()
            return func.HttpResponse(
                json.dumps({"message": "Employee deleted successfully"}),
                mimetype="application/json"
            )
        
        except Exception as e:
            db.rollback()
            logging.exception("DELETE failed")
            return func.HttpResponse(
                json.dumps({"error": str(e)}),
                status_code=500,
                mimetype="application/json"
            )
        
    return func.HttpResponse("Method not allowed", status_code=405)