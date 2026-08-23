from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import Base, SessionLocal, engine
from .migrations import run_startup_migrations
from .routers import dashboard, initiatives, notifications, references
from .seed import seed_data

app = FastAPI(title="AI Champions Portfolio Portal v2", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    run_startup_migrations(engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(references.router, tags=["references"])
app.include_router(initiatives.router, tags=["initiatives"])
app.include_router(dashboard.router, tags=["dashboard"])
app.include_router(notifications.router, tags=["notifications"])
