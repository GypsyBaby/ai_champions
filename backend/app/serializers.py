from . import models


def _latest_status(ini: models.Initiative):
    if not ini.approvals:
        return None
    latest = max(ini.approvals, key=lambda a: a.created_at)
    return latest.status


def _payback_months(ini: models.Initiative):
    """Planned cost (₽) ÷ expected monthly benefit (₽) — both derived from
    resource quantity × the resource's rate set by PM. None when there's no
    monthly benefit to divide by (payback is undefined, not infinite/zero)."""
    planned_cost_money = sum(
        e.quantity * (e.resource.rate if e.resource else 0)
        for e in ini.resource_entries if e.is_planned
    )
    benefit_money = sum(
        b.quantity * (b.resource.rate if b.resource else 0) for b in ini.benefits
    )
    if benefit_money <= 0:
        return None
    return planned_cost_money / benefit_money


def initiative_list_item(ini: models.Initiative) -> dict:
    return {
        "id": ini.id,
        "title": ini.title,
        "champion_id": ini.champion_id,
        "champion_name": ini.champion.full_name if ini.champion else None,
        "department_id": ini.department_id,
        "department_name": ini.department.name if ini.department else None,
        "start_date": ini.start_date,
        "end_date": ini.end_date,
        "is_approved": ini.is_approved,
        "approval_stage": ini.approval_stage,
        "latest_status": _latest_status(ini),
        "payback_months": _payback_months(ini),
        "created_at": ini.created_at,
        "updated_at": ini.updated_at,
    }


def _resource_entry_dict(entry: models.ResourceEntry, fact_by_resource: dict) -> dict:
    return {
        "id": entry.id,
        "resource_id": entry.resource_id,
        "resource_name": entry.resource.name if entry.resource else None,
        "category": entry.resource.category if entry.resource else None,
        "unit": entry.resource.unit if entry.resource else None,
        "quantity": entry.quantity,
        "is_planned": entry.is_planned,
        "fact_quantity": fact_by_resource.get(entry.resource_id, 0),
    }


def _benefit_dict(b: models.Benefit) -> dict:
    return {
        "id": b.id,
        "resource_id": b.resource_id,
        "resource_name": b.resource.name if b.resource else None,
        "category": b.resource.category if b.resource else None,
        "unit": b.resource.unit if b.resource else None,
        "quantity": b.quantity,
    }


def _comment_dict(c: models.Comment) -> dict:
    return {
        "id": c.id,
        "initiative_id": c.initiative_id,
        "author_id": c.author_id,
        "author_name": c.author.full_name if c.author else None,
        "text": c.text,
        "created_at": c.created_at,
    }


def _approval_dict(a: models.Approval) -> dict:
    return {
        "id": a.id,
        "initiative_id": a.initiative_id,
        "actor_id": a.actor_id,
        "actor_name": a.actor.full_name if a.actor else None,
        "actor_role": a.actor.role if a.actor else None,
        "actor_specialization": a.actor.led_resource.name if a.actor and a.actor.led_resource else None,
        "status": a.status,
        "comment": a.comment,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def _pending_approver_dict(p: models.PendingApprover) -> dict:
    return {
        "id": p.id,
        "employee_id": p.employee_id,
        "employee_name": p.employee.full_name if p.employee else None,
        "resource_id": p.resource_id,
        "resource_name": p.resource.name if p.resource else None,
        "status": p.status,
    }


def _attachment_dict(a: models.Attachment) -> dict:
    return {
        "id": a.id,
        "initiative_id": a.initiative_id,
        "uploader_id": a.uploader_id,
        "uploader_name": a.uploader.full_name if a.uploader else None,
        "filename": a.filename,
        "content_type": a.content_type,
        "size": a.size,
        "created_at": a.created_at,
    }


def _cost_log_dict(c: models.CostLog) -> dict:
    return {
        "id": c.id,
        "initiative_id": c.initiative_id,
        "resource_id": c.resource_id,
        "resource_name": c.resource.name if c.resource else None,
        "unit": c.resource.unit if c.resource else None,
        "champion_id": c.champion_id,
        "champion_name": c.champion.full_name if c.champion else None,
        "quantity": c.quantity,
        "created_at": c.created_at,
    }


def initiative_detail(ini: models.Initiative) -> dict:
    base = initiative_list_item(ini)
    base["description"] = ini.description

    fact_by_resource: dict = {}
    for log in ini.cost_logs:
        fact_by_resource[log.resource_id] = fact_by_resource.get(log.resource_id, 0) + log.quantity

    base["resources_planned"] = [
        _resource_entry_dict(e, fact_by_resource) for e in ini.resource_entries if e.is_planned
    ]
    base["benefits"] = [_benefit_dict(b) for b in ini.benefits]
    base["comments"] = sorted(
        [_comment_dict(c) for c in ini.comments], key=lambda c: c["created_at"]
    )
    base["approvals"] = sorted(
        [_approval_dict(a) for a in ini.approvals], key=lambda a: a["created_at"], reverse=True
    )
    base["cost_logs"] = sorted(
        [_cost_log_dict(c) for c in ini.cost_logs], key=lambda c: c["created_at"], reverse=True
    )
    base["pending_approvers"] = [_pending_approver_dict(p) for p in ini.pending_approvers]
    base["attachments"] = sorted(
        [_attachment_dict(a) for a in ini.attachments], key=lambda a: a["created_at"], reverse=True
    )
    return base
