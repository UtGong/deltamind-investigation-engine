# Trust Certificate API Contract

Base URL:

```text
http://localhost:8000
```

## Clean Trust Certificate Routes

```http
GET /api/v1/trust-certificates/recent?limit=20
GET /api/v1/trust-certificates/recent/status-cards?limit=20
GET /api/v1/trust-certificates/recent/dashboard-summary?limit=20
GET /api/v1/trust-certificates/{case_id}
GET /api/v1/trust-certificates/{case_id}/status-card
GET /api/v1/trust-certificates/{case_id}/lifecycle
GET /api/v1/trust-certificates/{case_id}/reverification-summary
```

## Filters

The recent status-card and dashboard-summary endpoints support:

```text
lifecycle_status=active|draft|revoked
action_required=none|reverify_available|review_required|issue_certificate
min_trust_index=0.6
has_been_reverified=true|false
```

Example:

```http
GET /api/v1/trust-certificates/recent/status-cards?limit=10&lifecycle_status=active
```

## Dashboard Summary Response

```json
{
  "requested_limit": 20,
  "filters": {
    "lifecycle_status": null,
    "action_required": null,
    "min_trust_index": null,
    "has_been_reverified": null
  },
  "certificate_count": 5,
  "by_lifecycle_status": {
    "active": 3,
    "draft": 2
  },
  "by_action_required": {
    "none": 1,
    "reverify_available": 2,
    "issue_certificate": 2
  },
  "active_count": 3,
  "revoked_count": 0,
  "draft_count": 2,
  "review_required_count": 0,
  "reverify_available_count": 2,
  "stable_count": 1,
  "average_trust_index": 0.6451
}
```

## Status Card Response

```json
{
  "certificate_id": "cert_...",
  "case_id": "case_...",
  "lifecycle_status": "active",
  "status_label": "Active",
  "action_required": "none",
  "overall_verdict": "contradicted",
  "confidence": 0.6932,
  "trust_index": 0.6451,
  "evidence_graph_id": "graph_...",
  "issued_at": "2026-06-29T17:54:11.351302Z",
  "updated_at": "2026-06-29T18:10:00.000000Z",
  "claim_count": 1,
  "evidence_count": 3,
  "source_count": 2,
  "independence_cluster_count": 2,
  "event_count": 4,
  "has_been_reverified": true,
  "latest_event_type": "reverified",
  "latest_reverification_event_type": "reverified",
  "timeline": []
}
```

## Lifecycle Actions

```http
POST /api/v1/trust-certificates/{case_id}/simulate-downgrade
POST /api/v1/trust-certificates/{case_id}/downgrade
POST /api/v1/trust-certificates/{case_id}/reactivate
POST /api/v1/trust-certificates/{case_id}/reverify
```

## Lifecycle Action Body

Used by:

```http
POST /api/v1/trust-certificates/{case_id}/simulate-downgrade
POST /api/v1/trust-certificates/{case_id}/downgrade
POST /api/v1/trust-certificates/{case_id}/reactivate
```

```json
{
  "reason": "Manual lifecycle action.",
  "metadata": {
    "trigger": "manual_test"
  }
}
```

## Reverification Body

Used by:

```http
POST /api/v1/trust-certificates/{case_id}/reverify
```

```json
{
  "reason": "Manual re-verification.",
  "metadata": {
    "trigger": "manual_reverify"
  },
  "trust_drop_threshold": 0.15,
  "minimum_active_trust_index": 0.5
}
```

## Lifecycle Event Types

```text
issued
downgrade_simulated
reactivated
reverified
reverification_downgraded
reverification_reactivated
```

## Compatibility Routes

Older compatibility routes may still exist under:

```http
/api/v1/cases/{case_id}/trust-certificate/...
```

The canonical frontend routes should use:

```http
/api/v1/trust-certificates/...
```
