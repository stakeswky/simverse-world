from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ChallengeState(StrEnum):
    INITIAL = "INITIAL"
    EVIDENCE_READY = "EVIDENCE_READY"
    PREVIEW_READY = "PREVIEW_READY"
    APPROVED_ONCE = "APPROVED_ONCE"
    COMMITTED = "COMMITTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class ChallengeResident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resident_id: str
    name: str
    cash_sc: int
    unpaid_wage_sc: int
    food_risk: Literal["LOW", "MEDIUM", "HIGH"]
    food_credit_sc: int
    stabilized: bool


class ChallengeEmployer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employer_id: str
    name: str
    overdue_payroll_sc: int
    repayment_claim_sc: int
    escrow_status: Literal["NONE", "PENDING", "MET", "MISSED"]


class ChallengeRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relationship_id: str
    source_id: str
    target_id: str
    direct_score: int
    tension: int


class ChallengeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    region_id: str
    title: str
    description: str
    occurs_at: datetime


class ChallengeMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unpaid_residents: int
    high_food_risk_residents: int
    social_tension: int
    strike_risk_pct: int
    stabilized_residents: int


class ChallengeWorld(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: Literal["harbor-wage-crisis-v1"]
    fixture_version: Literal[1]
    world_version: int
    world_time: datetime
    budget_sc: int
    harbor_open: bool
    residents: list[ChallengeResident]
    employers: list[ChallengeEmployer]
    relationships: list[ChallengeRelationship]
    events: list[ChallengeEvent]
    metrics: ChallengeMetrics
