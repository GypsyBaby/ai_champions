import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..database import DATA_DIR, get_db
from ..deps import get_current_employee, require_employee, require_role
from ..serializers import initiative_detail, initiative_list_item

ATTACHMENTS_DIR = os.path.join(DATA_DIR, "attachments")
MAX_ATTACHMENT_SIZE = 20 * 1024 * 1024  # 20 MB

router = APIRouter()


def _base_query(db: Session):
    return db.query(models.Initiative).options(
        joinedload(models.Initiative.champion),
        joinedload(models.Initiative.department),
        joinedload(models.Initiative.resource_entries).joinedload(models.ResourceEntry.resource),
        joinedload(models.Initiative.benefits).joinedload(models.Benefit.resource),
        joinedload(models.Initiative.comments).joinedload(models.Comment.author),
        joinedload(models.Initiative.approvals)
        .joinedload(models.Approval.actor)
        .joinedload(models.Employee.led_resource),
        joinedload(models.Initiative.cost_logs).joinedload(models.CostLog.resource),
        joinedload(models.Initiative.cost_logs).joinedload(models.CostLog.champion),
        joinedload(models.Initiative.pending_approvers).joinedload(models.PendingApprover.employee),
        joinedload(models.Initiative.pending_approvers).joinedload(models.PendingApprover.resource),
        joinedload(models.Initiative.attachments).joinedload(models.Attachment.uploader),
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


def _notify_top_management(db: Session, message: str):
    tops = db.query(models.Employee).filter(models.Employee.role == "top").all()
    for top in tops:
        _notify(db, top.id, message)


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
    awaiting_me: Optional[bool] = Query(default=None),
    db: Session = Depends(get_db),
    employee: Optional[models.Employee] = Depends(get_current_employee),
):
    q = _base_query(db)

    # For head/teamlead, "is_approved" from the frontend is really a tab
    # selector ("Требуют согласования" vs "Согласованные") relative to what
    # *they* decided, not a literal is_approved==bool filter — a head who
    # approved an initiative that's now waiting on TeamLeads (or a TeamLead
    # who approved while peers are still deciding) should still see it under
    # "Согласованные", even though the initiative as a whole isn't fully
    # approved yet. `role_scoped` marks that this endpoint already applied
    # the right condition, so the blanket is_approved filter below is skipped.
    role_scoped = employee is not None and employee.role in ("head", "teamlead")

    # Heads only ever see their own department, regardless of the requested filter.
    if employee is not None and employee.role == "head":
        department_id = employee.department_id
        if is_approved is False:
            # Not yet decided by the head (or rejected/sent back — those need
            # a fresh decision too). Excludes initiatives already routed to
            # TeamLeads, which aren't waiting on the head anymore.
            q = q.filter(models.Initiative.approval_stage == "head")
        elif is_approved is True:
            # The head approved it — either it's fully done, or it's now
            # further along the chain (waiting on TeamLeads or top management).
            q = q.filter(
                or_(
                    models.Initiative.is_approved == True,  # noqa: E712
                    models.Initiative.approval_stage.in_(["teamlead", "top"]),
                )
            )

    if champion_id:
        q = q.filter(models.Initiative.champion_id == champion_id)
    if department_id:
        q = q.filter(models.Initiative.department_id == department_id)
    if is_approved is not None and not role_scoped:
        q = q.filter(models.Initiative.is_approved == is_approved)

    # TeamLeads only ever see initiatives tied to their own specialization.
    if employee is not None and employee.role == "teamlead":
        if is_approved is False:
            ids = [
                row[0] for row in
                db.query(models.PendingApprover.initiative_id)
                .filter(
                    models.PendingApprover.employee_id == employee.id,
                    models.PendingApprover.status == "pending",
                )
                .distinct()
            ]
        else:
            # Initiatives this TeamLead personally approved (any overall
            # state — peers may still be deciding, or a peer may have since
            # rejected). Also covers initiatives approved before this
            # multi-step chain existed, which have no PendingApprover trail
            # at all but did plan this TeamLead's specialization.
            approved_by_me = {
                row[0] for row in
                db.query(models.PendingApprover.initiative_id)
                .filter(
                    models.PendingApprover.employee_id == employee.id,
                    models.PendingApprover.status == "approved",
                )
                .distinct()
            }
            legacy_approved = {
                row[0] for row in
                db.query(models.ResourceEntry.initiative_id)
                .join(models.Resource, models.Resource.id == models.ResourceEntry.resource_id)
                .join(models.Initiative, models.Initiative.id == models.ResourceEntry.initiative_id)
                .filter(
                    models.ResourceEntry.is_planned == True,  # noqa: E712
                    models.Resource.team_lead_id == employee.id,
                    models.Initiative.is_approved == True,  # noqa: E712
                )
                .distinct()
            }
            ids = approved_by_me | legacy_approved
        q = q.filter(models.Initiative.id.in_(ids or [-1]))

    # Top management's "Требуют согласования" tab: initiatives that made it
    # all the way through the head and every required TeamLead and are now
    # waiting on the final sign-off. Uses a separate `awaiting_me` param
    # (rather than overloading is_approved like head/teamlead above) since
    # top management's existing "Все инициативы" tab already uses is_approved
    # as a plain, unscoped filter and the two must not collide.
    if awaiting_me and employee is not None and employee.role == "top":
        q = q.filter(
            models.Initiative.approval_stage == "top",
            models.Initiative.is_approved == False,  # noqa: E712
        )

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
        # Restart the approval chain from the head — the planned specializations
        # may have changed, so any outstanding TeamLead decisions are stale.
        ini.approval_stage = "head"
        db.query(models.PendingApprover).filter(models.PendingApprover.initiative_id == ini.id).delete()
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
#
# Chain: champion submits -> department head decides -> if approved, routed to
# the TeamLead of every specialization planned in "Человеко-часы" -> once all
# of them approve, the initiative is fully approved (is_approved=True). A
# rejection or revision request at either step halts the chain immediately;
# editing planned resources/benefits afterwards restarts it from the head
# (see update_initiative).


def _required_teamleads(ini: models.Initiative) -> dict[int, int]:
    """{teamlead_employee_id: resource_id} for every human specialization that
    currently has a TeamLead assigned and is referenced either in "Человеко-часы"
    (planned resources) or "Ожидаемая выгода" (benefits) — either one puts that
    specialization's TeamLead in the approval chain."""
    result: dict[int, int] = {}
    for entry in ini.resource_entries:
        if (
            entry.is_planned
            and entry.resource
            and entry.resource.category == "human"
            and entry.resource.team_lead_id
        ):
            result[entry.resource.team_lead_id] = entry.resource_id
    for benefit in ini.benefits:
        if (
            benefit.resource
            and benefit.resource.category == "human"
            and benefit.resource.team_lead_id
        ):
            result[benefit.resource.team_lead_id] = benefit.resource_id
    return result


def _authorize_approver(db: Session, employee: models.Employee, ini: models.Initiative) -> str:
    """Returns "head", "teamlead" or "top" if the employee may currently
    decide on this initiative, otherwise raises 403."""
    if employee.role == "head":
        if employee.department_id != ini.department_id:
            raise HTTPException(status_code=403, detail="Вы не являетесь руководителем этого подразделения")
        if ini.approval_stage != "head":
            raise HTTPException(
                status_code=403,
                detail="Инициатива сейчас не ожидает решения руководителя",
            )
        return "head"
    if employee.role == "teamlead":
        row = (
            db.query(models.PendingApprover)
            .filter(
                models.PendingApprover.initiative_id == ini.id,
                models.PendingApprover.employee_id == employee.id,
            )
            .first()
        )
        if not row:
            raise HTTPException(
                status_code=403,
                detail="Вы не входите в число согласующих для этой инициативы",
            )
        if row.status != "pending":
            raise HTTPException(status_code=403, detail="Вы уже приняли решение по этой инициативе")
        return "teamlead"
    if employee.role == "top":
        if ini.approval_stage != "top":
            raise HTTPException(
                status_code=403,
                detail="Инициатива сейчас не ожидает решения топ-менеджмента",
            )
        return "top"
    raise HTTPException(
        status_code=403,
        detail="Согласование доступно только руководителю подразделения, TeamLead или топ-менеджменту",
    )


def _clear_pending_approvers(db: Session, initiative_id: int):
    """Wipe the whole round — used when the chain restarts from scratch (the
    champion editing planned resources/benefits, or the head starting a new
    TeamLead round). Removes even already-"approved" rows, since a changed
    resource list can make a prior round's decisions stale."""
    db.query(models.PendingApprover).filter(models.PendingApprover.initiative_id == initiative_id).delete()


def _halt_pending_round(db: Session, initiative_id: int):
    """A TeamLead rejected/requested revision: stop asking anyone still
    undecided, but keep rows already marked "approved" so those TeamLeads
    keep seeing the initiative under "Согласованные"."""
    db.query(models.PendingApprover).filter(
        models.PendingApprover.initiative_id == initiative_id,
        models.PendingApprover.status == "pending",
    ).delete()


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
    role_kind = _authorize_approver(db, employee, ini)

    db.add(models.Approval(
        initiative_id=ini.id, actor_id=employee.id, status="approved", comment=payload.comment or "",
    ))
    ini.updated_at = datetime.utcnow()

    if role_kind == "head":
        required = _required_teamleads(ini)
        if not required:
            # No human resources with a TeamLead planned — skip straight to
            # the final sign-off from top management.
            ini.approval_stage = "top"
            _notify_top_management(
                db, f"Инициатива «{ini.title}» согласована руководителем и ожидает вашего решения.",
            )
            _notify(
                db, ini.champion_id,
                f"Инициатива «{ini.title}» согласована руководителем и направлена топ-менеджменту.",
            )
        else:
            ini.approval_stage = "teamlead"
            _clear_pending_approvers(db, ini.id)
            for lead_id, resource_id in required.items():
                db.add(models.PendingApprover(
                    initiative_id=ini.id, employee_id=lead_id, resource_id=resource_id,
                ))
                _notify(
                    db, lead_id,
                    f"Инициатива «{ini.title}» согласована руководителем и ожидает вашего решения.",
                )
            _notify(
                db, ini.champion_id,
                f"Инициатива «{ini.title}» согласована руководителем и направлена TeamLead-ам на согласование.",
            )
    elif role_kind == "teamlead":
        db.query(models.PendingApprover).filter(
            models.PendingApprover.initiative_id == ini.id,
            models.PendingApprover.employee_id == employee.id,
        ).update({"status": "approved"})
        remaining = db.query(models.PendingApprover).filter(
            models.PendingApprover.initiative_id == ini.id,
            models.PendingApprover.status == "pending",
        ).count()
        if remaining == 0:
            ini.approval_stage = "top"
            _notify_top_management(
                db, f"Инициатива «{ini.title}» согласована всеми TeamLead-ами и ожидает вашего решения.",
            )
            _notify(
                db, ini.champion_id,
                f"Инициатива «{ini.title}» согласована всеми TeamLead-ами и направлена топ-менеджменту.",
            )
        else:
            _notify(
                db, ini.champion_id,
                f"TeamLead {employee.full_name} согласовал инициативу «{ini.title}». "
                f"Ожидает решения ещё {remaining} TeamLead(ов).",
            )
    else:  # top
        ini.is_approved = True
        _notify(db, ini.champion_id, f"Инициатива «{ini.title}» полностью согласована топ-менеджментом.")

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
    role_kind = _authorize_approver(db, employee, ini)

    db.add(models.Approval(
        initiative_id=ini.id, actor_id=employee.id, status="rejected", comment=payload.comment,
    ))
    ini.is_approved = False
    if role_kind in ("teamlead", "top"):
        # Only wipe rows still undecided — anyone (head or TeamLead) who
        # already approved earlier keeps that under their own "Согласованные".
        _halt_pending_round(db, ini.id)
    else:
        _clear_pending_approvers(db, ini.id)
    ini.updated_at = datetime.utcnow()
    _notify(db, ini.champion_id, f"Инициатива «{ini.title}» отклонена ({employee.full_name}).")

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
    role_kind = _authorize_approver(db, employee, ini)

    db.add(models.Approval(
        initiative_id=ini.id, actor_id=employee.id, status="revision", comment=payload.comment,
    ))
    ini.is_approved = False
    if role_kind in ("teamlead", "top"):
        # Only wipe rows still undecided — anyone (head or TeamLead) who
        # already approved earlier keeps that under their own "Согласованные".
        _halt_pending_round(db, ini.id)
    else:
        _clear_pending_approvers(db, ini.id)
    ini.updated_at = datetime.utcnow()
    _notify(db, ini.champion_id, f"Инициатива «{ini.title}» отправлена на пересмотр ({employee.full_name}).")

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

    # Fact hours logged against a specialization may never exceed its planned hours.
    planned_quantity = sum(
        e.quantity for e in ini.resource_entries
        if e.is_planned and e.resource_id == payload.resource_id
    )
    already_logged = sum(c.quantity for c in ini.cost_logs if c.resource_id == payload.resource_id)
    remaining = planned_quantity - already_logged
    if payload.quantity > remaining:
        resource_name = next(
            (e.resource.name for e in ini.resource_entries if e.resource_id == payload.resource_id and e.resource),
            "ресурс",
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Нельзя записать {payload.quantity:g} ч. по специализации «{resource_name}»: "
                f"план — {planned_quantity:g} ч., уже записано — {already_logged:g} ч., "
                f"остаётся не более {max(remaining, 0):g} ч."
            ),
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


# ---------- Attachments ----------


def _safe_original_filename(name: str) -> str:
    name = os.path.basename(name or "").strip()
    # Defend against header-injection via control characters in Content-Disposition.
    name = "".join(ch for ch in name if ch.isprintable())
    return name or "file"


@router.post("/initiatives/{initiative_id}/attachments", response_model=schemas.AttachmentRead)
async def upload_attachment(
    initiative_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_employee),
):
    ini = db.query(models.Initiative).get(initiative_id)
    if not ini:
        raise HTTPException(status_code=404, detail="Инициатива не найдена")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Файл пустой")
    if len(content) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Файл слишком большой: максимум {MAX_ATTACHMENT_SIZE // (1024 * 1024)} МБ",
        )

    original_name = _safe_original_filename(file.filename)
    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{original_name}"
    with open(os.path.join(ATTACHMENTS_DIR, stored_name), "wb") as f:
        f.write(content)

    attachment = models.Attachment(
        initiative_id=ini.id,
        uploader_id=employee.id,
        filename=original_name,
        stored_name=stored_name,
        content_type=file.content_type or "application/octet-stream",
        size=len(content),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return schemas.AttachmentRead(
        id=attachment.id, initiative_id=attachment.initiative_id, uploader_id=attachment.uploader_id,
        uploader_name=employee.full_name, filename=attachment.filename,
        content_type=attachment.content_type, size=attachment.size, created_at=attachment.created_at,
    )


@router.get("/initiatives/{initiative_id}/attachments/{attachment_id}/download")
def download_attachment(initiative_id: int, attachment_id: int, db: Session = Depends(get_db)):
    attachment = (
        db.query(models.Attachment)
        .filter(models.Attachment.id == attachment_id, models.Attachment.initiative_id == initiative_id)
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Файл не найден")
    path = os.path.join(ATTACHMENTS_DIR, attachment.stored_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Файл не найден на сервере")
    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.filename,
    )
