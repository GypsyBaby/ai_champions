from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from .database import Base

ROLES = ("champion", "head", "pm", "top")
RESOURCE_CATEGORIES = ("human", "tech")
APPROVAL_STATUSES = ("pending", "approved", "rejected", "revision")


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)

    employees = relationship("Employee", back_populates="department")
    initiatives = relationship("Initiative", back_populates="department")


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    position = Column(String, nullable=False, default="")
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    email = Column(String, nullable=False, default="")
    role = Column(String, nullable=False, index=True)  # champion / head / pm / top

    department = relationship("Department", back_populates="employees")


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    category = Column(String, nullable=False)  # human / tech
    unit = Column(String, nullable=False, default="")
    rate = Column(Float, nullable=False, default=0)  # cost per unit (e.g. RUB per чел-час), set by PM


class Initiative(Base):
    __tablename__ = "initiatives"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True, default="")
    champion_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_approved = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    champion = relationship("Employee", foreign_keys=[champion_id])
    department = relationship("Department", back_populates="initiatives")
    resource_entries = relationship(
        "ResourceEntry", back_populates="initiative", cascade="all, delete-orphan"
    )
    benefits = relationship("Benefit", back_populates="initiative", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="initiative", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="initiative", cascade="all, delete-orphan")
    cost_logs = relationship("CostLog", back_populates="initiative", cascade="all, delete-orphan")


class ResourceEntry(Base):
    __tablename__ = "resource_entries"

    id = Column(Integer, primary_key=True, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False)
    quantity = Column(Float, nullable=False, default=0)
    is_planned = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    initiative = relationship("Initiative", back_populates="resource_entries")
    resource = relationship("Resource")


class Benefit(Base):
    __tablename__ = "benefits"

    id = Column(Integer, primary_key=True, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False)
    quantity = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    initiative = relationship("Initiative", back_populates="benefits")
    resource = relationship("Resource")


class CostLog(Base):
    """History of actual human-hours logged against a planned specialization
    by the initiative's champion — powers the 'Фактические затраты' column."""

    __tablename__ = "cost_logs"

    id = Column(Integer, primary_key=True, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False)
    champion_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    initiative = relationship("Initiative", back_populates="cost_logs")
    resource = relationship("Resource")
    champion = relationship("Employee")


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False)
    # The employee who produced this record — usually the department head making a
    # decision, but also the champion when an edit auto-sends the initiative to revision.
    actor_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending/approved/rejected/revision
    comment = Column(Text, nullable=True, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    initiative = relationship("Initiative", back_populates="approvals")
    actor = relationship("Employee")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    initiative_id = Column(Integer, ForeignKey("initiatives.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    initiative = relationship("Initiative", back_populates="comments")
    author = relationship("Employee")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    message = Column(String, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
