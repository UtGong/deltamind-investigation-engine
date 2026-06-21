from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.session import Base

settings = get_settings()
VECTOR_DIM = settings.embedding_dimension


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CaseRecord(Base, TimestampMixin):
    __tablename__ = "cases"

    case_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    input_type: Mapped[str] = mapped_column(String(50), nullable=False)
    input_text: Mapped[str | None] = mapped_column(Text)
    input_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    case_verdict: Mapped[str | None] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float)
    investigation_result_json: Mapped[dict | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    claims: Mapped[list["ClaimRecord"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )


class ClaimRecord(Base, TimestampMixin):
    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.case_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_claim_text: Mapped[str | None] = mapped_column(Text, index=True)
    claim_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(Text)
    predicate: Mapped[str | None] = mapped_column(Text)
    object_value: Mapped[str | None] = mapped_column(Text)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decomposition_confidence: Mapped[float | None] = mapped_column(Float)
    final_verdict: Mapped[str | None] = mapped_column(String(80), index=True)
    correctness_score: Mapped[float | None] = mapped_column(Float)
    trust_score: Mapped[float | None] = mapped_column(Float)
    uncertainty_score: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    case: Mapped["CaseRecord"] = relationship(back_populates="claims")


class SourceRecord(Base, TimestampMixin):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    source_name: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(Text)
    reliability_prior: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class EvidenceRecord(Base, TimestampMixin):
    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    claim_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(160), index=True)
    query_id: Mapped[str | None] = mapped_column(String(120), index=True)
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_span_start: Mapped[int | None] = mapped_column(Integer)
    evidence_span_end: Mapped[int | None] = mapped_column(Integer)
    retrieval_method: Mapped[str | None] = mapped_column(String(120), index=True)
    source_type: Mapped[str | None] = mapped_column(String(80), index=True)
    independence_group: Mapped[str | None] = mapped_column(String(255), index=True)
    reliability: Mapped[float | None] = mapped_column(Float)
    independence: Mapped[float | None] = mapped_column(Float)
    freshness: Mapped[float | None] = mapped_column(Float)
    specificity: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class StanceRecord(Base, TimestampMixin):
    __tablename__ = "stances"

    stance_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    claim_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    stance_label: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(160))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class GraphEdgeRecord(Base, TimestampMixin):
    __tablename__ = "graph_edges"

    edge_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(String(80), index=True)
    src_node_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    src_node_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    dst_node_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    dst_node_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    edge_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    edge_weight: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "src_node_id",
            "dst_node_id",
            "edge_type",
            name="uq_graph_edges_src_dst_type",
        ),
    )


class AgentRunRecord(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    run_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    agent_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    output_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)


class CostLogRecord(Base, TimestampMixin):
    __tablename__ = "cost_logs"

    cost_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    cost_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(120), index=True)
    units: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unit_name: Mapped[str | None] = mapped_column(String(80))
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class LLMCacheRecord(Base, TimestampMixin):
    __tablename__ = "llm_cache"

    request_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    cache_namespace: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str | None] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class VerifiedClaimRecord(Base, TimestampMixin):
    __tablename__ = "verified_claims"

    normalized_claim_text: Mapped[str] = mapped_column(Text, primary_key=True)
    claim_hash: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)

    claim_text: Mapped[str | None] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    verdict: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Float)

    support_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    contradiction_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    uncertainty_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    correctness_score: Mapped[float | None] = mapped_column(Float)
    trust_score: Mapped[float | None] = mapped_column(Float)

    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    freshness_policy: Mapped[str] = mapped_column(String(120), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    evidence_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    stance_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ModelPredictionRecord(Base, TimestampMixin):
    __tablename__ = "model_predictions"

    prediction_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    claim_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    features_version: Mapped[str] = mapped_column(String(80), nullable=False)
    correctness_score: Mapped[float] = mapped_column(Float, nullable=False)
    trust_score: Mapped[float] = mapped_column(Float, nullable=False)
    uncertainty_score: Mapped[float] = mapped_column(Float, nullable=False)
    support_score: Mapped[float | None] = mapped_column(Float)
    contradiction_score: Mapped[float | None] = mapped_column(Float)
    verdict: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    features_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    prediction_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SourceReliabilityRecord(Base, TimestampMixin):
    __tablename__ = "source_reliability"

    reliability_id: Mapped[str] = mapped_column(String(220), primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    claim_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    topic: Mapped[str | None] = mapped_column(String(160), index=True)
    reliability_mean: Mapped[float] = mapped_column(Float, nullable=False)
    reliability_uncertainty: Mapped[float] = mapped_column(Float, nullable=False)
    num_observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "domain",
            "claim_type",
            "topic",
            name="uq_source_reliability_domain_claim_type_topic",
        ),
    )


class TrainingLabelRecord(Base, TimestampMixin):
    __tablename__ = "training_labels"

    label_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(80), index=True)
    label_source: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    correctness_label: Mapped[bool | None] = mapped_column(Boolean)
    verdict_label: Mapped[str | None] = mapped_column(String(80), index=True)
    trust_label: Mapped[float | None] = mapped_column(Float)
    annotator_id: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class ClaimEmbeddingRecord(Base, TimestampMixin):
    __tablename__ = "claim_embeddings"

    claim_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    embedding_model: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(VECTOR_DIM))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class EvidenceEmbeddingRecord(Base, TimestampMixin):
    __tablename__ = "evidence_embeddings"

    evidence_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    embedding_model: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(VECTOR_DIM))
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


Index("ix_evidence_claim_source", EvidenceRecord.claim_id, EvidenceRecord.source_id)
Index("ix_stances_claim_evidence", StanceRecord.claim_id, StanceRecord.evidence_id)
Index("ix_model_predictions_claim_model", ModelPredictionRecord.claim_id, ModelPredictionRecord.model_name)
Index("ix_graph_edges_case_type", GraphEdgeRecord.case_id, GraphEdgeRecord.edge_type)
