import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import Base, SessionLocal, engine
from .migrations import run_startup_migrations
from .reminders import maybe_run_weekly_reminders, resolve_reminder_weekday
from .routers import dashboard, initiatives, notifications, references, reports
from .seed import seed_data

app = FastAPI(title="AI Champions Portfolio Portal v2", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# How often the background loop checks whether it's time to send the weekly
# time-logging reminder. It only actually sends on the configured weekday
# (see REMINDER_WEEKDAY below), and at most once per calendar day — checking
# hourly is just how promptly it notices the day changed.
REMINDER_CHECK_INTERVAL_SECONDS = 3600


async def _reminder_loop():
    weekday = resolve_reminder_weekday(os.environ.get("REMINDER_WEEKDAY"))
    while True:
        db = SessionLocal()
        try:
            maybe_run_weekly_reminders(db, weekday)
        finally:
            db.close()
        await asyncio.sleep(REMINDER_CHECK_INTERVAL_SECONDS)


@app.on_event("startup")
async def on_startup():
    run_startup_migrations(engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()
    asyncio.create_task(_reminder_loop())


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(references.router, tags=["references"])
app.include_router(initiatives.router, tags=["initiatives"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(notifications.router, tags=["notifications"])
app.include_router(reports.router, tags=["reports"])
