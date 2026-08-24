from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from .. import models
from ..database import get_db
from ..deps import require_role
from ..serializers import initiative_list_item

router = APIRouter()


def _base_query(db: Session):
    return db.query(models.Initiative).options(
        joinedload(models.Initiative.champion),
        joinedload(models.Initiative.department),
        joinedload(models.Initiative.resource_entries).joinedload(models.ResourceEntry.resource),
        joinedload(models.Initiative.benefits).joinedload(models.Benefit.resource),
        joinedload(models.Initiative.cost_logs).joinedload(models.CostLog.resource),
        joinedload(models.Initiative.approvals),
    )


@router.get("/dashboard/head")
def dashboard_head(
    db: Session = Depends(get_db),
    employee: models.Employee = Depends(require_role("head")),
):
    initiatives = _base_query(db).filter(models.Initiative.department_id == employee.department_id).all()
    items = [initiative_list_item(i) for i in initiatives]
    pending = [i for i in items if not i["is_approved"]]
    approved = [i for i in items if i["is_approved"]]

    return {
        "department": {"id": employee.department_id, "name": employee.department.name if employee.department else None},
        "pending_count": len(pending),
        "approved_count": len(approved),
        "pending_initiatives": pending,
        "approved_initiatives": approved,
    }


@router.get("/dashboard/top")
def dashboard_top(db: Session = Depends(get_db)):
    initiatives = _base_query(db).all()
    approved_initiatives = [ini for ini in initiatives if ini.is_approved]

    total = len(initiatives)
    approved_count = len(approved_initiatives)
    pending_count = total - approved_count

    # All money/resource/payback figures below are scoped to approved
    # initiatives only — a proposal that's still pending, in revision, or
    # rejected isn't committed spend and shouldn't count toward the portfolio's
    # actual cost, benefit or payback economics.
    resources_planned = _sum_by_resource(
        (entry.resource, entry.quantity)
        for ini in approved_initiatives
        for entry in ini.resource_entries
        if entry.is_planned
    )
    benefits_total = _sum_by_resource(
        (b.resource, b.quantity) for ini in approved_initiatives for b in ini.benefits
    )

    # Status counts per department come from the whole portfolio (this is what
    # feeds the "согласовано / не согласовано" chart), independent of the
    # approved-only money aggregation below.
    dept_counts = defaultdict(lambda: {"initiatives_count": 0, "approved_count": 0, "pending_count": 0})
    for ini in initiatives:
        dept_name = ini.department.name if ini.department else "—"
        agg = dept_counts[dept_name]
        agg["initiatives_count"] += 1
        if ini.is_approved:
            agg["approved_count"] += 1
        else:
            agg["pending_count"] += 1

    dept_money = defaultdict(lambda: {
        "planned_cost_money": 0.0, "fact_cost_money": 0.0, "benefit_money": 0.0,
        "payback_months_sum": 0.0,
    })
    for ini in approved_initiatives:
        dept_name = ini.department.name if ini.department else "—"
        agg = dept_money[dept_name]
        # Money values: quantity × the resource's configured rate (₽ per unit),
        # set by PM in "Ресурсы и ставки". A resource with no rate set contributes 0.
        ini_planned_cost = sum(
            e.quantity * (e.resource.rate if e.resource else 0)
            for e in ini.resource_entries if e.is_planned
        )
        ini_fact_cost = sum(
            c.quantity * (c.resource.rate if c.resource else 0) for c in ini.cost_logs
        )
        ini_benefit = sum(
            b.quantity * (b.resource.rate if b.resource else 0) for b in ini.benefits
        )
        agg["planned_cost_money"] += ini_planned_cost
        agg["fact_cost_money"] += ini_fact_cost
        agg["benefit_money"] += ini_benefit
        # Department payback = sum of each approved initiative's own payback
        # period. Initiatives with no monthly benefit have no payback period to add.
        if ini_benefit > 0:
            agg["payback_months_sum"] += ini_planned_cost / ini_benefit

    empty_money = {"planned_cost_money": 0.0, "fact_cost_money": 0.0, "benefit_money": 0.0, "payback_months_sum": 0.0}
    by_department_list = [
        {"department": name, **counts, **dept_money.get(name, empty_money)}
        for name, counts in dept_counts.items()
    ]
    by_department_list.sort(key=lambda x: x["initiatives_count"], reverse=True)

    return {
        "total_initiatives": total,
        "approved_count": approved_count,
        "pending_count": pending_count,
        "total_planned_cost_money": sum(d["planned_cost_money"] for d in by_department_list),
        "total_fact_cost_money": sum(d["fact_cost_money"] for d in by_department_list),
        "total_benefit_money": sum(d["benefit_money"] for d in by_department_list),
        # Portfolio payback = sum of every approved initiative's own payback period,
        # same method as the per-department figures (which this is a sum of).
        "total_payback_months": sum(d["payback_months_sum"] for d in by_department_list),
        "resources_planned": resources_planned,
        "benefits_total": benefits_total,
        "by_department": by_department_list,
    }


def _sum_by_resource(pairs):
    """Sum quantities grouped by resource — never blended across resources,
    since each one has its own unit (чел-часы, ядра, ГБ, ТБ, ...). Also
    includes each resource's rate and the resulting money total (total × rate)."""
    agg = defaultdict(float)
    meta = {}
    for resource, quantity in pairs:
        if resource is None:
            continue
        agg[resource.name] += quantity
        meta[resource.name] = (resource.category, resource.unit, resource.rate)
    result = [
        {
            "resource": name, "category": meta[name][0], "unit": meta[name][1],
            "total": total, "rate": meta[name][2], "total_money": total * meta[name][2],
        }
        for name, total in agg.items()
    ]
    result.sort(key=lambda x: (x["category"], -x["total"]))
    return result
