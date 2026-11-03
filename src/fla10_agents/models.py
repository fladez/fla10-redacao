"""Modelos tipados iniciais para os dados do MVP."""

from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field, HttpUrl


class EventStatus(StrEnum):
    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    CONFLICTING = "conflicting"


class ClaimClassification(StrEnum):
    CONFIRMED = "confirmed"
    ATTRIBUTED = "attributed"
    CONTEXT = "context"
    ANALYSIS = "analysis"
    HYPOTHESIS = "hypothesis"
    UNCONFIRMED = "unconfirmed"


class EvidenceSource(BaseModel):
    url: HttpUrl
    source_type: str
    author_or_institution: str | None = None
    published_at: datetime | None = None
    accessed_at: datetime
    supports: list[str] = Field(default_factory=list)
    supporting_excerpt_or_data: str | None = None
    limitations: str | None = None


class SportsEvent(BaseModel):
    event_id: str
    sport: str
    category: str
    competition: str
    season: str | None = None
    stage: str | None = None
    home_team: str
    away_team: str
    starts_at_local: datetime
    timezone: str
    venue: str | None = None
    event_status: EventStatus
    sources: list[EvidenceSource] = Field(default_factory=list)
    last_verified_at: datetime


class EditorialProposal(BaseModel):
    proposal_id: str
    title: str
    event_id: str | None = None
    format: str
    editorial_question: str
    angle: str
    why_now: str
    confirmed_facts: list[str] = Field(default_factory=list)
    attributed_information: list[str] = Field(default_factory=list)
    questions_to_verify: list[str] = Field(default_factory=list)
    initial_sources: list[EvidenceSource] = Field(default_factory=list)
    related_published: list[str] = Field(default_factory=list)
    related_reserved: list[str] = Field(default_factory=list)
    redundancy_risk: str = "unknown"
    priority_recommendation: str = "normal"
    editorial_decision: str = "awaiting_human"


class ClaimEvidence(BaseModel):
    claim_id: str
    claim_text: str
    classification: ClaimClassification
    evidence: list[EvidenceSource] = Field(default_factory=list)
    independent_corroboration: str = "unknown"
    open_questions: list[str] = Field(default_factory=list)


class ResearchDossier(BaseModel):
    proposal_id: str
    editorial_question: str
    researched_at: datetime
    claims: list[ClaimEvidence] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    usable_facts: list[str] = Field(default_factory=list)
    attribution_required: list[str] = Field(default_factory=list)
    admissible_analysis: list[str] = Field(default_factory=list)
    excluded_claims: list[str] = Field(default_factory=list)
    recommendation: str
