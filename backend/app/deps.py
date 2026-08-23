from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from . import models
from .database import get_db


def get_current_employee(
    x_employee_id: Optional[int] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[models.Employee]:
    if x_employee_id is None:
        return None
    return db.query(models.Employee).get(x_employee_id)


def require_employee(
    employee: Optional[models.Employee] = Depends(get_current_employee),
) -> models.Employee:
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется заголовок X-Employee-ID с корректным сотрудником",
        )
    return employee


def require_role(*roles: str):
    def _dep(employee: models.Employee = Depends(require_employee)) -> models.Employee:
        if employee.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Действие доступно только для ролей: {', '.join(roles)}",
            )
        return employee

    return _dep
