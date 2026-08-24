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
        specialization=e.led_resource.name if e.led_resource else None,
    )


@router.get("/employees", response_model=list[schemas.EmployeeRead])
def list_employees(db: Session = Depends(get_db)):
    employees = (
        db.query(models.Employee)
        .options(joinedload(models.Employee.department), joinedload(models.Employee.led_resource))
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


def _resource_read(r: models.Resource) -> schemas.ResourceRead:
    return schemas.ResourceRead(
        id=r.id,
        name=r.name,
        category=r.category,
        unit=r.unit,
        rate=r.rate,
        team_lead_id=r.team_lead_id,
        team_lead_name=r.team_lead.full_name if r.team_lead else None,
    )


def _validate_team_lead(db: Session, team_lead_id: int, exclude_resource_id: int | None = None) -> models.Employee:
    lead = db.query(models.Employee).get(team_lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Сотрудник-тимлид не найден")
    if lead.role != "teamlead":
        raise HTTPException(status_code=400, detail="Указанный сотрудник должен иметь роль TeamLead")
    taken = (
        db.query(models.Resource)
        .filter(models.Resource.team_lead_id == team_lead_id)
        .filter(models.Resource.id != exclude_resource_id if exclude_resource_id else True)
        .first()
    )
    if taken:
        raise HTTPException(
            status_code=400,
            detail=f"Этот TeamLead уже назначен для специализации «{taken.name}»",
        )
    return lead


@router.get("/resources", response_model=list[schemas.ResourceRead])
def list_resources(db: Session = Depends(get_db)):
    resources = db.query(models.Resource).order_by(models.Resource.category, models.Resource.name).all()
    return [_resource_read(r) for r in resources]


@router.post("/resources", response_model=schemas.ResourceRead)
def create_resource(
    payload: schemas.ResourceCreate,
    db: Session = Depends(get_db),
    _employee: models.Employee = Depends(require_role("pm")),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Название специализации/ресурса не может быть пустым")
    if payload.category not in models.RESOURCE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Категория должна быть одной из: {', '.join(models.RESOURCE_CATEGORIES)}")
    if db.query(models.Resource).filter(models.Resource.name == name).first():
        raise HTTPException(status_code=400, detail="Ресурс с таким названием уже существует")
    if (payload.rate or 0) < 0:
        raise HTTPException(status_code=400, detail="Ставка не может быть отрицательной")

    if payload.category == "human":
        if not payload.team_lead_id:
            raise HTTPException(
                status_code=400,
                detail="Для новой специализации необходимо указать сотрудника с ролью TeamLead",
            )
        _validate_team_lead(db, payload.team_lead_id)

    resource = models.Resource(
        name=name,
        category=payload.category,
        unit=(payload.unit or "").strip(),
        rate=payload.rate or 0,
        team_lead_id=payload.team_lead_id if payload.category == "human" else None,
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return _resource_read(resource)


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
    updates = payload.model_dump(exclude_unset=True)
    if "rate" in updates:
        if updates["rate"] < 0:
            raise HTTPException(status_code=400, detail="Ставка не может быть отрицательной")
        resource.rate = updates["rate"]
    if "team_lead_id" in updates:
        new_lead_id = updates["team_lead_id"]
        if resource.category == "human" and not new_lead_id:
            raise HTTPException(status_code=400, detail="У специализации должен быть назначен TeamLead")
        if new_lead_id:
            _validate_team_lead(db, new_lead_id, exclude_resource_id=resource.id)
            resource.team_lead_id = new_lead_id
        else:
            resource.team_lead_id = None
    db.commit()
    db.refresh(resource)
    return _resource_read(resource)
