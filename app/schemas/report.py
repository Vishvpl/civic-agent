import uuid
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, field_validator

class IncomingReport(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., pattern=r"^image/(jpeg|png|webp)$")

class BoundingBox(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    width: float = Field(..., gt=0.0, le=1.0)
    height: float = Field(..., gt=0.0, le=1.0)


class PerceptionResult(BaseModel):
    report_id: uuid.UUID
    issue_detected: bool
    issue_label: str | None = None          # e.g. "pothole", "broken_streetlight"
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    bounding_box: BoundingBox | None = None
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    captured_at: datetime | None = None
    low_confidence: bool = False

    @field_validator("low_confidence", mode="before")
    @classmethod
    def derive_low_confidence(cls, v, info):
        return v

class RecommendedTool(str, Enum):
    SEND_REPORT = "send_civic_report"
    LOG_LEDGER = "log_to_official_ledger"
    GEOCODE = "reverse_geocode"


class ActionPlan(BaseModel):
    report_id: uuid.UUID
    issue_type: str = Field(..., min_length=1)
    statute_ref: str | None = None          # e.g. "Municipal Code §14.2.3"
    severity: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    recommended_tools: list[RecommendedTool] = Field(..., min_length=1)
    context_summary: str = Field(..., min_length=10, max_length=1000)
    requires_human_review: bool = False

class ReportResponse(BaseModel):
    id: uuid.UUID
    status: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportDetail(BaseModel):
    id: uuid.UUID
    status: str
    original_filename: str
    gps_latitude: float | None
    gps_longitude: float | None
    captured_at: datetime | None
    confidence_score: float | None
    perception_result: dict[str, Any] | None
    action_plan: dict[str, Any] | None
    action_result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}