"""Weekly reminder for AI-champions to log actual time spent on their
initiatives. Runs as a background loop started at app startup (see main.py):
every hour it checks whether today is the configured weekday and whether the
job hasn't already run today, and if so sends one reminder notification per
champion who still has unlogged planned human-hours on an approved initiative.
"""

import logging
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from . import models

logger = logging.getLogger("reminders")

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DEFAULT_REMINDER_WEEKDAY = "thursday"


def resolve_reminder_weekday(raw: Optional[str]) -> int:
    """Accepts a weekday name (any case, e.g. "Thursday") or an integer
    0-6 (Monday=0); falls back to Thursday for anything else."""
    raw = (raw or "").strip().lower()
    if raw in WEEKDAY_NAMES:
        return WEEKDAY_NAMES.index(raw)
    try:
        n = int(raw)
        if 0 <= n <= 6:
            return n
    except ValueError:
        pass
    if raw:
        logger.warning("Invalid REMINDER_WEEKDAY=%r, defaulting to %s", raw, DEFAULT_REMINDER_WEEKDAY)
    return WEEKDAY_NAMES.index(DEFAULT_REMINDER_WEEKDAY)


def champions_needing_reminder(db: Session) -> list[tuple[models.Employee, list[str]]]:
    """AI-champions with at least one approved initiative that still has
    planned human-hours not yet fully logged. Returns [(employee, [titles])]."""
    champions = db.query(models.Employee).filter(models.Employee.role == "champion").all()
    result = []
    for champ in champions:
        initiatives = (
            db.query(models.Initiative)
            .filter(
                models.Initiative.champion_id == champ.id,
                models.Initiative.is_approved == True,  # noqa: E712
            )
            .all()
        )
        titles = []
        for ini in initiatives:
            fact_by_resource: dict = {}
            for log in ini.cost_logs:
                fact_by_resource[log.resource_id] = fact_by_resource.get(log.resource_id, 0) + log.quantity
            has_remaining = any(
                e.is_planned and e.resource and e.resource.category == "human"
                and e.quantity > fact_by_resource.get(e.resource_id, 0)
                for e in ini.resource_entries
            )
            if has_remaining:
                titles.append(ini.title)
        if titles:
            result.append((champ, titles))
    return result


def send_weekly_time_logging_reminders(db: Session) -> int:
    """Creates one "reminder" notification per AI-champion who needs one.
    Returns how many reminders were sent."""
    sent = 0
    for champ, titles in champions_needing_reminder(db):
        preview = ", ".join(f"«{t}»" for t in titles[:3])
        if len(titles) > 3:
            preview += f" и ещё {len(titles) - 3}"
        message = (
            f"Напоминание: пора залогировать фактическое время по инициативам — {preview}."
        )
        db.add(models.Notification(recipient_id=champ.id, message=message, type="reminder"))
        sent += 1
    db.commit()
    return sent


def maybe_run_weekly_reminders(db: Session, weekday: int, today: Optional[date] = None) -> bool:
    """Runs the reminder job if today matches the configured weekday and it
    hasn't already run today. Returns whether it actually ran."""
    today = today or date.today()
    if today.weekday() != weekday:
        return False
    already_ran = db.query(models.ReminderRun).filter(models.ReminderRun.run_date == today).first()
    if already_ran:
        return False
    sent = send_weekly_time_logging_reminders(db)
    db.add(models.ReminderRun(run_date=today))
    db.commit()
    logger.info("Weekly time-logging reminders sent: %d", sent)
    return True
