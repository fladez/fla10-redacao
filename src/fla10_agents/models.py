"""Modelos tipados iniciais para os dados do MVP."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


def _require_aware_datetime(value: datetime | None) -> datetime | None:
    if value is not None and value.utcoffset() is None:
        raise ValueError("A data/hora precisa conter fuso ou offset explícito.")
    return value


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

    @field_validator("published_at", "accessed_at")
    @classmethod
    def validate_source_dates(cls, value: datetime | None) -> datetime | None:
        return _require_aware_datetime(value)


class SportsEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    sport: str
    category: str
    competition: str
    season: str | None = None
    stage: str | None = None
    home_team: str
    away_team: str
    starts_at_local: datetime | None = None
    timezone: str
    venue: str | None = None
    event_status: EventStatus
    sources: list[EvidenceSource] = Field(default_factory=list)
    last_verified_at: datetime

    @field_validator("starts_at_local")
    @classmethod
    def validate_local_start(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError(
                "starts_at_local deve ser horário local sem offset; informe o fuso em timezone."
            )
        return value

    @model_validator(mode="after")
    def validate_confirmed_start(self) -> "SportsEvent":
        if self.event_status == EventStatus.CONFIRMED and self.starts_at_local is None:
            raise ValueError(
                "Evento confirmado exige data e hora locais (starts_at_local). "
                "Sem data definida, use o status provisional."
            )
        return self

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Fuso horário IANA inválido: {value}") from exc
        return value

    @field_validator("last_verified_at")
    @classmethod
    def validate_verification_date(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)  # type: ignore[return-value]


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
    window: str | None = None
    dedupe_key: str | None = None
    created_at: datetime | None = None

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime | None) -> datetime | None:
        return _require_aware_datetime(value)


class MonitoringSignal(BaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    provider: str
    external_id: str
    title: str
    summary: str | None = None
    url: HttpUrl | None = None
    published_at: datetime
    topics: list[str] = Field(default_factory=list)
    teams: list[str] = Field(default_factory=list)
    players: list[str] = Field(default_factory=list)
    last_seen_at: datetime

    @field_validator("published_at", "last_seen_at")
    @classmethod
    def validate_signal_dates(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)  # type: ignore[return-value]


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

    @field_validator("researched_at")
    @classmethod
    def validate_research_date(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)  # type: ignore[return-value]


class SeoPackage(BaseModel):
    title: str
    meta_description: str
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)


class DraftArticle(BaseModel):
    draft_id: str = Field(default_factory=lambda: str(uuid4()))
    proposal_id: str
    format: str
    title: str
    subtitle: str
    body_markdown: str
    body_html: str
    ai_summary: str | None = None
    seo: SeoPackage
    social_posts: list[str] = Field(default_factory=list)
    sources: list[EvidenceSource] = Field(default_factory=list)
    model: str
    prompt_version: str = "writing-v1"
    prompt_sha256: str | None = None
    generation: dict[str, object] = Field(default_factory=dict)
    editorial_decision: str = "awaiting_human"
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_draft_date(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)  # type: ignore[return-value]


class ReviewIssue(BaseModel):
    severity: Literal["critico", "alto", "medio", "baixo"]
    category: str
    description: str
    evidence: str | None = None


class ReviewReport(BaseModel):
    review_id: str = Field(default_factory=lambda: str(uuid4()))
    draft_id: str
    verdict: str
    issues: list[ReviewIssue] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    summary: str = ""
    reviewer_model: str
    prompt_version: str = "review-v1"
    prompt_sha256: str | None = None
    generation: dict[str, object] = Field(default_factory=dict)
    reviewed_at: datetime

    @field_validator("reviewed_at")
    @classmethod
    def validate_review_date(cls, value: datetime) -> datetime:
        return _require_aware_datetime(value)  # type: ignore[return-value]


class PublicationPackage(BaseModel):
    package_id: str = Field(default_factory=lambda: str(uuid4()))
    draft_id: str
    format: str
    title: str
    subtitle: str
    slug: str
    body_html: str
    body_markdown: str
    ai_summary: str | None = None
    seo: SeoPackage
    social_posts: list[str] = Field(default_factory=list)
    sources: list[EvidenceSource] = Field(default_factory=list)
    status: str = "prepared"
    created_at: datetime
    exported_at: datetime | None = None
    published_at: datetime | None = None
    url: HttpUrl | None = None
    confirmation: str | None = None

    @field_validator("created_at", "exported_at", "published_at")
    @classmethod
    def validate_package_dates(cls, value: datetime | None) -> datetime | None:
        return _require_aware_datetime(value)
