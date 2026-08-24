from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ---------- References ----------


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class DepartmentCreate(BaseModel):
    name: str


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    position: str
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    email: str
    role: str
    specialization: Optional[str] = None


class EmployeeCreate(BaseModel):
    full_name: str
    position: Optional[str] = ""
    email: Optional[str] = ""
    role: str
    department_id: Optional[int] = None


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    position: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    department_id: Optional[int] = None


class ResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: str
    unit: str
    rate: float = 0
    team_lead_id: Optional[int] = None
    team_lead_name: Optional[str] = None


class ResourceCreate(BaseModel):
    name: str
    category: str
    unit: Optional[str] = ""
    rate: Optional[float] = 0
    team_lead_id: Optional[int] = None


class ResourceRateUpdate(BaseModel):
    rate: Optional[float] = None
    team_lead_id: Optional[int] = None


# ---------- Resource entries / benefits ----------


class ResourceEntryIn(BaseModel):
    resource_id: int
    quantity: float


class ResourceEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int
    resource_name: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    quantity: float
    is_planned: bool
    fact_quantity: float = 0


class BenefitIn(BaseModel):
    resource_id: int
    quantity: float


class BenefitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    resource_id: int
    resource_name: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    quantity: float


# ---------- Initiatives ----------


class InitiativeCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    champion_id: int
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    resources: List[ResourceEntryIn] = []
    benefits: List[BenefitIn] = []


class InitiativeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    resources: Optional[List[ResourceEntryIn]] = None
    benefits: Optional[List[BenefitIn]] = None


class InitiativeListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    champion_id: int
    champion_name: Optional[str] = None
    department_id: int
    department_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_approved: bool
    approval_stage: str
    latest_status: Optional[str] = None
    payback_months: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class InitiativeListResponse(BaseModel):
    items: List[InitiativeListItem]
    total: int


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    initiative_id: int
    actor_id: int
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    actor_specialization: Optional[str] = None
    status: str
    comment: Optional[str] = ""
    created_at: datetime
    updated_at: datetime


class CommentCreate(BaseModel):
    text: str


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    initiative_id: int
    author_id: int
    author_name: Optional[str] = None
    text: str
    created_at: datetime


class CostLogCreate(BaseModel):
    resource_id: int
    quantity: float


class CostLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    initiative_id: int
    resource_id: int
    resource_name: Optional[str] = None
    unit: Optional[str] = None
    champion_id: int
    champion_name: Optional[str] = None
    quantity: float
    created_at: datetime


class PendingApproverRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    resource_id: Optional[int] = None
    resource_name: Optional[str] = None
    status: str


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    initiative_id: int
    uploader_id: int
    uploader_name: Optional[str] = None
    filename: str
    content_type: str
    size: int
    created_at: datetime


class InitiativeDetail(InitiativeListItem):
    description: Optional[str] = ""
    resources_planned: List[ResourceEntryRead] = []
    benefits: List[BenefitRead] = []
    comments: List[CommentRead] = []
    approvals: List[ApprovalRead] = []
    cost_logs: List[CostLogRead] = []
    pending_approvers: List[PendingApproverRead] = []
    attachments: List[AttachmentRead] = []


class ApprovalAction(BaseModel):
    comment: Optional[str] = ""


# ---------- Notifications ----------


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recipient_id: int
    message: str
    type: str = "info"
    is_read: bool
    created_at: datetime
