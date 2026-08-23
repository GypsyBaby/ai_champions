from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_employee, require_employee, require_role
from ..serializers import initiative_detail, initiative_list_item

router = APIRouter()


def _base_query(db: Session):
    return db.query(models.Initiative).options(
        joinedload(models.Initiative.champion),
        joinedload(models.Initiative.department),
        joinedload(models.Initiative.resource_entries).joinedload(models.ResourceEntry.resource),
        joinedload(models.Initiative.benefits).joinedload(models.Benefit.resource),
        joinedload(models.Initiative.comments).joinedload(models.Comment.author),
        joinedload(models.Initiative.approvals).joinedload(models.Approval.actor),
        joinedload(models.Initiative.cost_logs).joinedload(models.CostLog.resource),
        joinedload(models.Initiative.cost_logs).joinedload(models.CostLog.champion),
    )


def _get_or_404(db: Session, initiative_id: int) -> models.Initiative:
    obj = _base_query(db).filter(models.Initiative.id == initiative_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Инициатива не найдена")
    return obj


def _notify(db: Session, recipient_id: int, message: str):
    db.add(models.Notification(recipient_id=recipient_id, message=message))


def _notify_department_heads(db: Session, department_id: int, message: str):
    heads = (
        db.query(models.Employee)
        .filter(models.Employee.role == "head", models.Employee.department_id == department_id)
        .all()
    )
    for head in heads:
        _notify(db, head.id, message)


def _fmt_qty(q: float) -> str:
    return f"{q:g}"


def _diff_lines(old_pairs, new_pairs, resource_map: dict) -> list[str]:
    """Describe what changed between two (resource_id, quantity) collections,
    one line per resource that was added, removed, or changed in quantity."""
    old_map = dict(old_pairs)
    new_map = dict(new_pairs)
    lines = []
    for resource_id in sorted(set(old_map) | set(new_map)):
        old_qty = old_map.get(resource_id)
        new_qty = new_map.get(resource_id)
        if old_qty == new_qty:
            continue
        resource = resource_map.get(resource_id)
        name = resource.name if resource else f"#{resource_id}"
        unit = resource.unit if resource else ""
        if old_qty is None:
            lines.append(f"{name}: добавлено {_fmt_qty(new_qty)} {unit}".strip())
        elif new_qty is None:
            lines.append(f"{name}: убрано (было {_fmt_qty(old_qty)} {unit})".strip())
        else:
            lines.append(f"{name}: {_fmt_qty(old_qty)} → {_fmt_qty(new_qty)} {unit}".strip())
    return lines


@router.get("/initiatives", response_model=schemas.InitiativeListResponse)
def list_initiatives(
    champion_id: Optional[int] = Query(default=None),
    department_id: Optional[int] = Query(default=None),
    is_approved: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    employee: Optional[models.Employee] = Depends(get_current_employee),
):
    q = _base_query(db)

    # Heads only ever see their own department, regardless of the requested filter.
    if employee is not None and employee.role == "head":
        department_id = employee.department_id

    if champion_id:
        q = q.filter(models.Initiative.champion_id == champion_id)
    if department_id:
        q = q.filter(models.Initiative.department_id == department_id)
    if is_approved is not None:
        q = q.filter(models.Initiative.is_approved == is_approved)

    items = q.order_by(models.Initiative.updated_at.desc()).all()
    return schemas.InitiativeListResponse(
        items=[initiative_list_item(i) for i in items],
        total=len(items),
    )


@router.get("/initiatives/{initiative_id}", response_model=schemas.InitiativeDetail)
def get_initiative(initiative_id: int, db: Session = Depends(get_db)):
    ini = _get_or_404(db, initiative_id)
    return initiative_detail(ini)


@router.post("/initiatives", response_model=schemas.InitiativeDetail)
def create_initiative(
    payload: schemas.InitiativeCreate,
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_role("champion")),
):
    if payload.champion_id != employee.id:
        raise HTTPException(status_code=403, detail="Можно создавать инициативы только от своего имени")
    if not employee.department_id:
        raise HTTPException(status_code=400, detail="У чемпиона не задано подразделение")

    ini = models.Initiative(
        title=payload.title,
        description=payload.description or "",
        champion_id=employee.id,
        department_id=employee.department_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(ini)
    db.flush()

    for r in payload.resources:
        db.add(models.ResourceEntry(
            initiative_id=ini.id, resource_id=r.resource_id, quantity=r.quantity, is_planned=True,
        ))
    for b in payload.benefits:
        db.add(models.Benefit(initiative_id=ini.id, resource_id=b.resource_id, quantity=b.quantity))

    _notify_department_heads(
        db, employee.department_id,
        f"Новая инициатива «{ini.title}» от {employee.full_name} ожидает согласования.",
    )

    db.commit()
    return initiative_detail(_get_or_404(db, ini.id))


@router.put("/initiatives/{initiative_id}", response_model=schemas.InitiativeDetail)
def update_initiative(
    initiative_id: int,
    payload: schemas.InitiativeUpdate,
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_employee),
):
    ini = db.query(models.Initiative).get(initiative_id)
    if not ini:
        raise HTTPException(status_code=404, detail="Инициатива не найдена")
    if ini.champion_id != employee.id:
        raise HTTPException(status_code=403, detail="Редактировать инициативу может только её чемпион")

    if payload.title is not None:
        ini.title = payload.title
    if payload.description is not None:
        ini.description = payload.description
    if payload.start_date is not None:
        ini.start_date = payload.start_date
    if payload.end_date is not None:
        ini.end_date = payload.end_date

    resource_map = {r.id: r for r in db.query(models.Resource).all()}

    resource_diff = []
    if payload.resources is not None:
        old_pairs = [(e.resource_id, e.quantity) for e in ini.resource_entries if e.is_planned]
        new_pairs = [(r.resource_id, r.quantity) for r in payload.resources]
        resource_diff = _diff_lines(old_pairs, new_pairs, resource_map)

        db.query(models.ResourceEntry).filter(
            models.ResourceEntry.initiative_id == ini.id, models.ResourceEntry.is_planned == True  # noqa: E712
        ).delete()
        for r in payload.resources:
            db.add(models.ResourceEntry(
                initiative_id=ini.id, resource_id=r.resource_id, quantity=r.quantity, is_planned=True,
            ))

    benefit_diff = []
    if payload.benefits is not None:
        old_pairs = [(b.resource_id, b.quantity) for b in ini.benefits]
        new_pairs = [(b.resource_id, b.quantity) for b in payload.benefits]
        benefit_diff = _diff_lines(old_pairs, new_pairs, resource_map)

        db.query(models.Benefit).filter(models.Benefit.initiative_id == ini.id).delete()
        for b in payload.benefits:
            db.add(models.Benefit(initiative_id=ini.id, resource_id=b.resource_id, quantity=b.quantity))

    ini.updated_at = datetime.utcnow()

    # Editing planned resources or the expected benefit always sends the
    # initiative back for the head's review, with a record of exactly what
    # changed — regardless of what state it was in before (approved, rejected,
    # already pending, ...).
    if resource_diff or benefit_diff:
        ini.is_approved = False
        comment_sections = []
        if resource_diff:
            comment_sections.append("Плановые ресурсы:\n" + "\n".join(resource_diff))
        if benefit_diff:
            comment_sections.append("Ожидаемая выгода:\n" + "\n".join(benefit_diff))

        db.add(models.Approval(
            initiative_id=ini.id, actor_id=employee.id, status="revision",
            comment="Отправлено на пересмотр чемпионом в связи с изменением ресурсов/выгоды.\n\n"
            + "\n\n".join(comment_sections),
        ))
        _notify_department_heads(
            db, ini.department_id,
            f"Инициатива «{ini.title}» отправлена на пересмотр: изменены плановые ресурсы или ожидаемая выгода.",
        )
    else:
        _notify_department_heads(db, ini.department_id, f"Инициатива «{ini.title}» была изменена чемпионом.")

    db.commit()
    return initiative_detail(_get_or_404(db, initiative_id))


@router.delete("/initiatives/{initiative_id}")
def delete_initiative(
    initiative_id: int,
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_employee),
):
    ini = db.query(models.Initiative).get(initiative_id)
    if not ini:
        raise HTTPException(status_code=404, detail="Инициатива не найдена")
    if employee.role != "pm" and employee.id != ini.champion_id:
        raise HTTPException(status_code=403, detail="Удалить инициативу может только её чемпион или PM")
    db.delete(ini)
    db.commit()
    return {"ok": True}


# ---------- Approval workflow ----------


def _require_head_of_department(db: Session, employee: models.Employee, ini: models.Initiative):
    if employee.role != "head":
        raise HTTPException(status_code=403, detail="Согласование доступно только руководителю подразделения")
    if employee.department_id != ini.department_id:
        raise HTTPException(status_code=403, detail="Вы не являетесь руководителем этого подразделения")


@router.post("/initiatives/{initiative_id}/approve", response_model=schemas.InitiativeDetail)
def approve_initiative(
    initiative_id: int,
    payload: schemas.ApprovalAction,
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_employee),
):
    ini = db.query(models.Initiative).get(initiative_id)
    if not ini:
        raise HTTPException(status_code=404, detail="Инициатива не найдена")
    _require_head_of_department(db, employee, ini)

    db.add(models.Approval(
        initiative_id=ini.id, actor_id=employee.id, status="approved", comment=payload.comment or "",
    ))
    ini.is_approved = True
    ini.updated_at = datetime.utcnow()
    _notify(db, ini.champion_id, f"Инициатива «{ini.title}» согласована руководителем.")

    db.commit()
    return initiative_detail(_get_or_404(db, initiative_id))


@router.post("/initiatives/{initiative_id}/reject", response_model=schemas.InitiativeDetail)
def reject_initiative(
    initiative_id: int,
    payload: schemas.ApprovalAction,
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_employee),
):
    if not payload.comment or not payload.comment.strip():
        raise HTTPException(status_code=400, detail="При отклонении комментарий обязателен")
    ini = db.query(models.Initiative).get(initiative_id)
    if not ini:
        raise HTTPException(status_code=404, detail="Инициатива не найдена")
    _require_head_of_department(db, employee, ini)

    db.add(models.Approval(
        initiative_id=ini.id, actor_id=employee.id, status="rejected", comment=payload.comment,
    ))
    ini.is_approved = False
    ini.updated_at = datetime.utcnow()
    _notify(db, ini.champion_id, f"Инициатива «{ini.title}» отклонена руководителем.")

    db.commit()
    return initiative_detail(_get_or_404(db, initiative_id))


@router.post("/initiatives/{initiative_id}/revision", response_model=schemas.InitiativeDetail)
def request_revision(
    initiative_id: int,
    payload: schemas.ApprovalAction,
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_employee),
):
    if not payload.comment or not payload.comment.strip():
        raise HTTPException(status_code=400, detail="При отправке на пересмотр комментарий обязателен")
    ini = db.query(models.Initiative).get(initiative_id)
    if not ini:
        raise HTTPException(status_code=404, detail="Инициатива не найдена")
    _require_head_of_department(db, employee, ini)

    db.add(models.Approval(
        initiative_id=ini.id, actor_id=employee.id, status="revision", comment=payload.comment,
    ))
    ini.is_approved = False
    ini.updated_at = datetime.utcnow()
    _notify(db, ini.champion_id, f"Инициатива «{ini.title}» отправлена на пересмотр.")

    db.commit()
    return initiative_detail(_get_or_404(db, initiative_id))


# ---------- Time logging (actual human-hours) ----------


@router.post("/initiatives/{initiative_id}/cost_logs", response_model=schemas.InitiativeDetail)
def log_cost(
    initiative_id: int,
    payload: schemas.CostLogCreate,
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_employee),
):
    ini = db.query(models.Initiative).get(initiative_id)
    if not ini:
        raise HTTPException(status_code=404, detail="Инициатива не найдена")
    if ini.champion_id != employee.id:
        raise HTTPException(status_code=403, detail="Логировать время может только чемпион инициативы")
    if payload.quantity is None or payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Количество часов должно быть больше нуля")

    planned_human_resource_ids = {
        e.resource_id for e in ini.resource_entries
        if e.is_planned and e.resource and e.resource.category == "human"
    }
    if payload.resource_id not in planned_human_resource_ids:
        raise HTTPException(
            status_code=400,
            detail="Эта специализация не входит в плановые человеческие ресурсы инициативы",
        )

    db.add(models.CostLog(
        initiative_id=ini.id, resource_id=payload.resource_id, champion_id=employee.id,
        quantity=payload.quantity,
    ))
    db.commit()
    return initiative_detail(_get_or_404(db, initiative_id))


# ---------- Comments ----------


@router.get("/initiatives/{initiative_id}/comments", response_model=list[schemas.CommentRead])
def list_comments(initiative_id: int, db: Session = Depends(get_db)):
    comments = (
        db.query(models.Comment)
        .options(joinedload(models.Comment.author))
        .filter(models.Comment.initiative_id == initiative_id)
        .order_by(models.Comment.created_at)
        .all()
    )
    return [
        schemas.CommentRead(
            id=c.id, initiative_id=c.initiative_id, author_id=c.author_id,
            author_name=c.author.full_name if c.author else None,
            text=c.text, created_at=c.created_at,
        )
        for c in comments
    ]


@router.post("/initiatives/{initiative_id}/comments", response_model=schemas.CommentRead)
def add_comment(
    initiative_id: int,
    payload: schemas.CommentCreate,
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_employee),
):
    ini = db.query(models.Initiative).get(initiative_id)
    if not ini:
        raise HTTPException(status_code=404, detail="Инициатива не найдена")
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="Текст комментария не может быть пустым")

    comment = models.Comment(initiative_id=initiative_id, author_id=employee.id, text=payload.text.strip())
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return schemas.CommentRead(
        id=comment.id, initiative_id=comment.initiative_id, author_id=comment.author_id,
        author_name=employee.full_name, text=comment.text, created_at=comment.created_at,
    )
