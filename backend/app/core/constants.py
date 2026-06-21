from enum import StrEnum


class CaseStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class InputType(StrEnum):
    CLAIM = "claim"
    ARTICLE_TEXT = "article_text"
    URL = "url"


class ClaimType(StrEnum):
    EVENT = "event"
    NUMERIC = "numeric"
    QUOTE = "quote"
    ENTITY_RELATIONSHIP = "entity_relationship"
    TRANSFER = "transfer"
    INJURY = "injury"
    SCHEDULE = "schedule"
    RESULT = "result"
    CAUSAL = "causal"
    PREDICTION = "prediction"
    POLICY = "policy"
    HISTORICAL = "historical"
    UNKNOWN = "unknown"


class StanceLabel(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    PARTIALLY_SUPPORTS = "partially_supports"
    IRRELEVANT = "irrelevant"
    INSUFFICIENT = "insufficient"


class VerdictLabel(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    PARTIALLY_SUPPORTED = "partially_supported"
    OUTDATED = "outdated"
    MISLEADING = "misleading"
    UNVERIFIABLE = "unverifiable"
    CONTESTED = "contested"


class SourceType(StrEnum):
    OFFICIAL = "official"
    PRIMARY = "primary"
    TRUSTED_MEDIA = "trusted_media"
    MEDIA = "media"
    AGGREGATOR = "aggregator"
    SOCIAL = "social"
    DATABASE = "database"
    UNKNOWN = "unknown"


class AgentRunStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class CostType(StrEnum):
    AGENT = "agent"
    SEARCH = "search"
    DATABASE = "database"
    STORAGE = "storage"
    OTHER = "other"
