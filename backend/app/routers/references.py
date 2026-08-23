from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..deps import require_role

router = APIRouter()


@router.get("/departments", response_model=list[schemas.DepartmentRead])
def list_departments(db: Session = Depends(get_db)):
    return db.query(models.Department).order_by(models.Department.name).all()


@router.post("/departments", response_model=schemas.DepartmentRead)
def create_department(
    payload: schemas.DepartmentCreate,
    db: Session = Depends(get_db),
    _employee: models.Employee = Depends(require_role("pm")),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название подразделения не может быть пустым")
    if db.query(models.Department).filter(models.Department.name == name).first():
        raise HTTPException(status_code=400, detail="Подразделение с таким названием уже существует")
    dept = models.Department(name=name)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


def _employee_read(e: models.Employee) -> schemas.EmployeeRead:
    return schemas.EmployeeRead(
        id=e.id,
        full_name=e.full_name,
        position=e.position,
        department_id=e.department_id,
        department_name=e.department.name if e.department else None,
        email=e.email,
        role=e.role,
    )


@router.get("/employees", response_model=list[schemas.EmployeeRead])
def list_employees(db: Session = Depends(get_db)):
    employees = (
        db.query(models.Employee)
        .options(joinedload(models.Employee.department))
        .order_by(models.Employee.full_name)
        .all()
    )
    return [_employee_read(e) for e in employees]


@router.post("/employees", response_model=schemas.EmployeeRead)
def create_employee(
    payload: schemas.EmployeeCreate,
    db: Session = Depends(get_db),
    _employee: models.Employee = Depends(require_role("pm")),
):
    full_name = payload.full_name.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Имя сотрудника не может быть пустым")
    if payload.role not in models.ROLES:
        raise HTTPException(status_code=400, detail=f"Роль должна быть одной из: {', '.join(models.ROLES)}")
    if payload.department_id is not None and not db.query(models.Department).get(payload.department_id):
        raise HTTPException(status_code=404, detail="Подразделение не найдено")

    employee = models.Employee(
        full_name=full_name,
        position=(payload.position or "").strip(),
        email=(payload.email or "").strip(),
        role=payload.role,
        department_id=payload.department_id,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return _employee_read(employee)


@router.put("/employees/{employee_id}", response_model=schemas.EmployeeRead)
def update_employee(
    employee_id: int,
    payload: schemas.EmployeeUpdate,
    db: Session = Depends(get_db),
    _employee: models.Employee = Depends(require_role("pm")),
):
    employee = db.query(models.Employee).get(employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    updates = payload.model_dump(exclude_unset=True)
    if "role" in updates and updates["role"] not in models.ROLES:
        raise HTTPException(status_code=400, detail=f"Роль должна быть одной из: {', '.join(models.ROLES)}")
    if updates.get("department_id") is not None and not db.query(models.Department).get(updates["department_id"]):
        raise HTTPException(status_code=404, detail="Подразделение не найдено")
    if "full_name" in updates and not updates["full_name"].strip():
        raise HTTPException(status_code=400, detail="Имя сотрудника не может быть пустым")

    for field, value in updates.items():
        setattr(employee, field, value)

    db.commit()
    db.refresh(employee)
    return _employee_read(employee)


@router.get("/resources", response_model=list[schemas.ResourceRead])
def list_resources(db: Session = Depends(get_db)):
    return db.query(models.Resource).order_by(models.Resource.category, models.Resource.name).all()


@router.put("/resources/{resource_id}", response_model=schemas.ResourceRead)
def update_resource_rate(
    resource_id: int,
    payload: schemas.ResourceRateUpdate,
    db: Session = Depends(get_db),
    _employee: models.Employee = Depends(require_role("pm")),
):
    resource = db.query(models.Resource).get(resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Ресурс не найден")
    if payload.rate < 0:
        raise HTTPException(status_code=400, detail="Ставка не может быть отрицательной")
    resource.rate = payload.rate
    db.commit()
    db.refresh(resource)
    return resource
