from datetime import datetime, timedelta

from app.core.constants import ClaimType
from app.domain.cases.models import utc_now


TTL_DAYS_BY_CLAIM_TYPE: dict[ClaimType, int] = {
    ClaimType.RESULT: 3650,
    ClaimType.HISTORICAL: 3650,
    ClaimType.QUOTE: 365,
    ClaimType.POLICY: 180,
    ClaimType.EVENT: 90,
    ClaimType.ENTITY_RELATIONSHIP: 90,
    ClaimType.NUMERIC: 30,
    ClaimType.TRANSFER: 30,
    ClaimType.SCHEDULE: 7,
    ClaimType.INJURY: 2,
    ClaimType.PREDICTION: 1,
    ClaimType.CAUSAL: 30,
    ClaimType.UNKNOWN: 7,
}


POLICY_NAME_BY_CLAIM_TYPE: dict[ClaimType, str] = {
    ClaimType.RESULT: "stable_result_long_ttl",
    ClaimType.HISTORICAL: "stable_historical_long_ttl",
    ClaimType.QUOTE: "quote_medium_ttl",
    ClaimType.POLICY: "policy_medium_ttl",
    ClaimType.EVENT: "event_medium_ttl",
    ClaimType.ENTITY_RELATIONSHIP: "entity_relationship_medium_ttl",
    ClaimType.NUMERIC: "numeric_short_ttl",
    ClaimType.TRANSFER: "transfer_short_ttl",
    ClaimType.SCHEDULE: "schedule_very_short_ttl",
    ClaimType.INJURY: "injury_very_short_ttl",
    ClaimType.PREDICTION: "prediction_very_short_ttl",
    ClaimType.CAUSAL: "causal_short_ttl",
    ClaimType.UNKNOWN: "unknown_short_ttl",
}


def get_cache_ttl_days(claim_type: ClaimType) -> int:
    return TTL_DAYS_BY_CLAIM_TYPE.get(claim_type, TTL_DAYS_BY_CLAIM_TYPE[ClaimType.UNKNOWN])


def get_freshness_policy(claim_type: ClaimType) -> str:
    return POLICY_NAME_BY_CLAIM_TYPE.get(
        claim_type,
        POLICY_NAME_BY_CLAIM_TYPE[ClaimType.UNKNOWN],
    )


def compute_expires_at(
    claim_type: ClaimType,
    verified_at: datetime | None = None,
) -> datetime:
    base_time = verified_at or utc_now()
    ttl_days = get_cache_ttl_days(claim_type)
    return base_time + timedelta(days=ttl_days)


def is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False

    return expires_at <= utc_now()
