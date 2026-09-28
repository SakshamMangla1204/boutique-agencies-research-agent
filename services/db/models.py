"""ORM models for the AI agency / AI Engineer job research agent.

Tables (per project spec):
  agencies         - boutique/small/mid-size recruitment & staffing agencies
  contacts         - decision makers / recruitment leads (public info only)
  hiring_demand    - AI/technical hiring evidence + AI demand score
  research_sources - every source URL used for an agency
  job_openings     - AI Engineer roadmap-relevant job openings

Design notes
------------
* Deduplication keys are stored explicitly so the dedupe rules are visible in
  the schema: `normalized_domain` (primary) / `normalized_name` (fallback) for
  agencies, and `normalized_job_url` (primary) / `dedupe_fallback_key`
  (agency + title + client + location) for job openings.
* Counts that are unknowable are stored as NULL.  The pipeline never invents a
  job count; `estimated_ai_positions` stays NULL unless evidence exists.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.db.base import Base


class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    agency_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Normalized (lowercased, suffix-stripped) name for the fallback dedupe path.
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)

    domain: Mapped[str | None] = mapped_column(Text)
    # Normalized domain is the PRIMARY dedupe key.
    normalized_domain: Mapped[str | None] = mapped_column(Text)

    country: Mapped[str | None] = mapped_column(String(120))
    primary_city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    service_area: Mapped[str | None] = mapped_column(Text)
    ncr_presence: Mapped[str | None] = mapped_column(String(40))
    agency_type: Mapped[str | None] = mapped_column(String(120))
    linkedin: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    # Discovery-priority fields.  Geographic scoring is deliberately kept
    # SEPARATE from the AI-demand score.
    geographic_tier: Mapped[str | None] = mapped_column(String(60))
    geographic_priority_score: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="agency", cascade="all, delete-orphan"
    )
    hiring_demand: Mapped["HiringDemand | None"] = relationship(
        back_populates="agency", cascade="all, delete-orphan", uselist=False
    )
    research_sources: Mapped[list["ResearchSource"]] = relationship(
        back_populates="agency", cascade="all, delete-orphan"
    )
    job_openings: Mapped[list["JobOpening"]] = relationship(
        back_populates="agency", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("normalized_domain", name="uq_agencies_normalized_domain"),
        UniqueConstraint("normalized_name", name="uq_agencies_normalized_name"),
    )


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    linkedin: Mapped[str | None] = mapped_column(Text)
    # NEVER fabricated: only publicly published addresses, with source_url set.
    email: Mapped[str | None] = mapped_column(Text)
    email_type: Mapped[str | None] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agency: Mapped["Agency"] = relationship(back_populates="contacts")

    __table_args__ = (
        UniqueConstraint(
            "agency_id", "name", "role", name="uq_contacts_agency_name_role"
        ),
    )


class HiringDemand(Base):
    __tablename__ = "hiring_demand"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False
    )

    technical_recruitment: Mapped[bool | None] = mapped_column(Boolean)
    ai_recruitment: Mapped[bool | None] = mapped_column(Boolean)
    genai_recruitment: Mapped[bool | None] = mapped_column(Boolean)
    contract_staffing: Mapped[bool | None] = mapped_column(Boolean)
    bulk_hiring: Mapped[bool | None] = mapped_column(Boolean)

    active_ai_roles: Mapped[int | None] = mapped_column(Integer)
    # Never fabricated: NULL when there is no evidence for a count.
    estimated_ai_positions: Mapped[int | None] = mapped_column(Integer)

    ai_roles: Mapped[str | None] = mapped_column(Text)
    technologies: Mapped[str | None] = mapped_column(Text)
    client_industries: Mapped[str | None] = mapped_column(Text)
    bulk_hiring_evidence: Mapped[str | None] = mapped_column(Text)

    ai_demand_level: Mapped[str | None] = mapped_column(String(40))
    ai_demand_score: Mapped[int | None] = mapped_column(Integer)

    evidence_date: Mapped[str | None] = mapped_column(String(40))

    agency: Mapped["Agency"] = relationship(back_populates="hiring_demand")

    __table_args__ = (
        UniqueConstraint("agency_id", name="uq_hiring_demand_agency"),
    )


class ResearchSource(Base):
    __tablename__ = "research_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[int] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False
    )

    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(60))
    source_title: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agency: Mapped["Agency"] = relationship(back_populates="research_sources")

    __table_args__ = (
        UniqueConstraint(
            "agency_id", "source_url", name="uq_research_sources_agency_url"
        ),
    )


class JobOpening(Base):
    __tablename__ = "job_openings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agency_id: Mapped[int | None] = mapped_column(
        ForeignKey("agencies.id", ondelete="CASCADE")
    )

    # Dedupe keys.
    normalized_job_url: Mapped[str | None] = mapped_column(Text, index=True)
    dedupe_fallback_key: Mapped[str | None] = mapped_column(Text, index=True)

    job_title: Mapped[str | None] = mapped_column(Text)
    job_role: Mapped[str | None] = mapped_column(Text)
    company_or_client: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    remote_status: Mapped[str | None] = mapped_column(String(60))
    employment_type: Mapped[str | None] = mapped_column(String(80))
    experience_required: Mapped[str | None] = mapped_column(String(120))
    salary: Mapped[str | None] = mapped_column(Text)

    job_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    posted_date: Mapped[str | None] = mapped_column(String(40))

    # AI Engineer roadmap relevance.
    job_relevance: Mapped[str | None] = mapped_column(String(40), index=True)
    job_relevance_score: Mapped[int | None] = mapped_column(Integer)
    relevance_reason: Mapped[str | None] = mapped_column(Text)

    required_skills: Mapped[str | None] = mapped_column(Text)
    preferred_skills: Mapped[str | None] = mapped_column(Text)
    technologies: Mapped[str | None] = mapped_column(Text)
    ai_domain: Mapped[str | None] = mapped_column(String(80))

    llm: Mapped[bool | None] = mapped_column(Boolean)
    genai: Mapped[bool | None] = mapped_column(Boolean)
    rag: Mapped[bool | None] = mapped_column(Boolean)
    agents: Mapped[bool | None] = mapped_column(Boolean)
    nlp: Mapped[bool | None] = mapped_column(Boolean)
    computer_vision: Mapped[bool | None] = mapped_column(Boolean)
    model_integration: Mapped[bool | None] = mapped_column(Boolean)
    ai_application_development: Mapped[bool | None] = mapped_column(Boolean)

    fresher_friendly: Mapped[str | None] = mapped_column(String(20))

    # How the relevance label was produced: "heuristic" or "llm".
    relevance_source: Mapped[str | None] = mapped_column(String(20))
    relevance_confidence: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    agency: Mapped["Agency | None"] = relationship(back_populates="job_openings")

    __table_args__ = (
        UniqueConstraint("normalized_job_url", name="uq_job_openings_normalized_url"),
        UniqueConstraint(
            "agency_id",
            "dedupe_fallback_key",
            name="uq_job_openings_agency_fallback",
        ),
    )
