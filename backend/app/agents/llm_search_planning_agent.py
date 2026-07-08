import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel

from app.agents.base import Agent
from app.core.config import get_settings
from app.core.constants import ClaimType, SourceType
from app.domain.source_reliability.service import SourceReliabilityService
from app.providers.llm.base import LLMProvider
from app.providers.llm.mock_provider import MockLLMProvider
from app.schemas.agent import AtomicClaim
from app.schemas.llm import LLMMessage, LLMRequest, LLMResponse
from app.schemas.search import SearchPlan, SearchQuery, SourceCandidate


class LLMSearchPlanningInput(BaseModel):
    claim: AtomicClaim


class LLMSearchPlanningOutput(BaseModel):
    search_plan: SearchPlan
    raw_response: LLMResponse


@dataclass(frozen=True)
class ValidationProfile:
    subject: str
    context: str | None
    terms: list[str]
    candidate_domains: list[tuple[str, SourceType, str]]


class LLMSearchPlanningAgent(
    Agent[LLMSearchPlanningInput, LLMSearchPlanningOutput]
):
    name = "llm_search_planning_agent"

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or MockLLMProvider()

    def run(self, input_data: LLMSearchPlanningInput) -> LLMSearchPlanningOutput:
        settings = get_settings()
        claim = input_data.claim

        request = LLMRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are a search planning agent for a fact verification system. "
                        "Your job is to decide what evidence should be retrieved. "
                        "You do not verify the claim yourself. "
                        "You do not use memory as evidence. "
                        "You only produce a retrieval plan. "
                        "Return valid JSON only."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=(
                        "Create a retrieval plan for the claim below.\n\n"
                        "Core policy:\n"
                        "1. Prefer zero-cost direct source fetching first.\n"
                        "2. Include source_candidates for likely authoritative or useful sources.\n"
                        "3. If you know a stable, exact URL that is likely to contain the evidence, include it in source_candidates.url.\n"
                        "4. If you are not reasonably confident about the exact URL, set url to null.\n"
                        "5. Do not invent URLs just to fill the field. It is acceptable for url to be null.\n"
                        "6. Domain/source authority must be expressed by this planner, not by the search provider.\n"
                        "7. Search queries should be neutral retrieval requests, not verdicts.\n"
                        "8. Paid search should be requested only when free/direct retrieval is unlikely to be enough.\n"
                        "9. For query.provider, use configured_free_provider for free queries and configured_paid_provider for paid queries.\n"
                        "10. Do not use provider names like mock unless the user explicitly asks for mock mode.\n"
                        "11. Never output placeholder domains such as example.com, example.org, test.com, localhost, or invalid domains.\n\n"
                        "Decomposition policy:\n"
                        "- Keep the central subject/event in every query. Do not query only a fragment like a score.\n"
                        "- Identify validation terms such as matchup, date, round, score, quote, amount, entity, location, and source-of-record.\n"
                        "- For each validation term, include the central subject/event plus that term in a query.\n"
                        "- If the claim implies a competition or domain from context, state it as a hypothesis in the query rather than omitting it.\n\n"
                        "Do not copy domains, URLs, or sports leagues from examples or prior runs. "
                        "Choose domains from the actual claim context.\n\n"
                        "Allowed expected_source_type values:\n"
                        "- official\n"
                        "- primary\n"
                        "- trusted_media\n"
                        "- media\n"
                        "- aggregator\n"
                        "- social\n"
                        "- database\n"
                        "- unknown\n\n"
                        "Return exactly this JSON object shape:\n"
                        "{\n"
                        '  "source_candidates": [\n'
                        "    {\n"
                        '      "name": "string or null",\n'
                        '      "domain": "string or null",\n'
                        '      "url": "string or null",\n'
                        '      "expected_source_type": "official",\n'
                        '      "rationale": "string",\n'
                        '      "priority": 1\n'
                        "    }\n"
                        "  ],\n"
                        '  "queries": [\n'
                        "    {\n"
                        '      "query": "string",\n'
                        '      "purpose": "string",\n'
                        '      "cost_tier": "free",\n'
                        '      "expected_source_type": "official",\n'
                        '      "target_domains": [],\n'
                        '      "provider": "configured_free_provider"\n'
                        "    }\n"
                        "  ],\n"
                        '  "should_use_paid_search": false,\n'
                        '  "paid_search_rationale": "string or null",\n'
                        '  "max_paid_search_calls": 0\n'
                        "}\n\n"
                        f"Claim ID: {claim.claim_id}\n"
                        f"Claim text: {claim.claim_text}\n"
                        f"Claim type: {claim.claim_type}\n"
                        f"Subject: {claim.subject}\n"
                        f"Predicate: {claim.predicate}\n"
                        f"Object: {claim.object}\n"
                    ),
                ),
            ],
            temperature=0.0,
            response_format="json",
        )

        response = self.llm_provider.generate(request)

        search_plan = self._parse_search_plan(
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            claim=claim,
            content=response.content,
        )

        return LLMSearchPlanningOutput(
            search_plan=search_plan,
            raw_response=response,
        )

    def _parse_search_plan(
        self,
        claim_id: str,
        claim_text: str,
        claim: AtomicClaim | None,
        content: str,
    ) -> SearchPlan:
        payload = self._safe_json_loads(content)

        if payload is None or not isinstance(payload, dict):
            return self._fallback_plan(claim_id, claim_text, claim=claim)

        source_candidates = self._parse_source_candidates(
            payload.get("source_candidates", [])
        )
        queries = self._parse_queries(
            claim_id=claim_id,
            raw_queries=payload.get("queries", []),
        )

        if not source_candidates and not queries:
            return self._fallback_plan(claim_id, claim_text, claim=claim)

        should_use_paid_search = bool(payload.get("should_use_paid_search", False))
        max_paid_search_calls = self._parse_nonnegative_int(
            payload.get("max_paid_search_calls"),
            default=0,
        )

        search_plan = SearchPlan(
            claim_id=claim_id,
            source_candidates=source_candidates,
            queries=queries,
            should_use_paid_search=should_use_paid_search,
            paid_search_rationale=payload.get("paid_search_rationale"),
            max_paid_search_calls=max_paid_search_calls,
        )

        return self._sanitize_and_enrich_plan(search_plan, claim_text, claim=claim)

    def _parse_source_candidates(self, raw_candidates: object) -> list[SourceCandidate]:
        if not isinstance(raw_candidates, list):
            return []

        candidates: list[SourceCandidate] = []

        for raw_candidate in raw_candidates:
            if not isinstance(raw_candidate, dict):
                continue

            rationale = str(raw_candidate.get("rationale") or "").strip()
            if not rationale:
                rationale = "Planner-proposed source candidate."

            candidates.append(
                SourceCandidate(
                    name=self._optional_str(raw_candidate.get("name")),
                    domain=self._optional_str(raw_candidate.get("domain")),
                    url=self._optional_url(raw_candidate.get("url")),
                    expected_source_type=self._parse_source_type(
                        raw_candidate.get("expected_source_type")
                    ),
                    rationale=rationale,
                    priority=self._parse_priority(raw_candidate.get("priority")),
                    source_confidence=self._parse_confidence(
                        raw_candidate.get("source_confidence"),
                        default=0.5,
                    ),
                    confidence_source=str(raw_candidate.get("confidence_source") or "planner"),
                    validation_terms=self._parse_terms(raw_candidate.get("validation_terms")),
                )
            )

        return candidates

    def _parse_queries(
        self,
        claim_id: str,
        raw_queries: object,
    ) -> list[SearchQuery]:
        if not isinstance(raw_queries, list):
            return []

        queries: list[SearchQuery] = []

        for index, raw_query in enumerate(raw_queries, start=1):
            if not isinstance(raw_query, dict):
                continue

            query_text = str(raw_query.get("query") or "").strip()
            if not query_text:
                continue

            cost_tier = str(raw_query.get("cost_tier") or "free").strip().lower()
            if cost_tier not in {"free", "paid"}:
                cost_tier = "free"

            provider = str(raw_query.get("provider") or "").strip()
            if not provider or provider == "mock":
                provider = (
                    "configured_paid_provider"
                    if cost_tier == "paid"
                    else "configured_free_provider"
                )

            target_domains = raw_query.get("target_domains", [])
            if not isinstance(target_domains, list):
                target_domains = []

            queries.append(
                SearchQuery(
                    query_id=f"{claim_id}_query_{index}",
                    claim_id=claim_id,
                    query=query_text,
                    purpose=str(raw_query.get("purpose") or "Planner-generated search query."),
                    cost_tier=cost_tier,
                    expected_source_type=self._parse_source_type(
                        raw_query.get("expected_source_type")
                    ),
                    target_domains=[
                        str(domain).strip().lower()
                        for domain in target_domains
                        if str(domain).strip()
                    ],
                    provider=provider,
                    validation_terms=self._parse_terms(raw_query.get("validation_terms")),
                )
            )

        return queries

    def _safe_json_loads(self, content: str) -> dict | None:
        cleaned = content.strip()

        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()

        try:
            payload = json.loads(cleaned)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            pass

        object_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if object_match:
            try:
                payload = json.loads(object_match.group(0))
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                return None

        return None

    def _fallback_plan(
        self,
        claim_id: str,
        claim_text: str,
        *,
        claim: AtomicClaim | None = None,
    ) -> SearchPlan:
        profile = self._build_validation_profile(claim_text, claim=claim)

        return SearchPlan(
            claim_id=claim_id,
            source_candidates=self._source_candidates_for_profile(profile),
            queries=self._queries_for_profile(claim_id, claim_text, profile),
            should_use_paid_search=False,
            paid_search_rationale="Fallback plan avoids paid search.",
            max_paid_search_calls=0,
        )

    def _parse_source_type(self, value: object) -> SourceType:
        normalized = str(value or "").strip().lower()

        try:
            return SourceType(normalized)
        except ValueError:
            return SourceType.UNKNOWN

    def _parse_priority(self, value: object) -> int:
        try:
            priority = int(value)
        except (TypeError, ValueError):
            return 5

        return max(1, min(10, priority))

    def _parse_confidence(self, value: object, *, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default

        return max(0.0, min(1.0, parsed))

    def _parse_nonnegative_int(self, value: object, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default

        return max(0, parsed)

    def _parse_terms(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []

        terms = []
        for item in value:
            term = str(item).strip()
            if term:
                terms.append(term)

        return terms[:8]

    def _optional_str(self, value: object) -> str | None:
        if value is None:
            return None

        cleaned = str(value).strip()
        return cleaned or None

    def _optional_url(self, value: object) -> str | None:
        cleaned = self._optional_str(value)

        if not cleaned:
            return None

        if cleaned.lower() in {"null", "none", "unknown", "n/a"}:
            return None

        if not cleaned.startswith(("http://", "https://")):
            return None

        return cleaned

    def _sanitize_and_enrich_plan(
        self,
        plan: SearchPlan,
        claim_text: str,
        *,
        claim: AtomicClaim | None,
    ) -> SearchPlan:
        profile = self._build_validation_profile(claim_text, claim=claim)

        source_candidates = [
            self._enrich_candidate(candidate, profile)
            for candidate in plan.source_candidates
            if self._is_usable_candidate(candidate, profile)
        ]
        queries = [
            query
            for query in plan.queries
            if self._is_usable_query(query, profile)
        ]

        fallback = self._fallback_plan(plan.claim_id, claim_text, claim=claim)

        domains = {
            self._normalize_domain(candidate.domain or candidate.url)
            for candidate in source_candidates
        }
        for candidate in fallback.source_candidates:
            domain = self._normalize_domain(candidate.domain or candidate.url)
            if domain and domain not in domains:
                source_candidates.append(candidate)
                domains.add(domain)

        if len(queries) < len(profile.terms):
            query_texts = {query.query.lower() for query in queries}
            for query in fallback.queries:
                if query.query.lower() not in query_texts:
                    queries.append(query)
                    query_texts.add(query.query.lower())

        return plan.model_copy(
            update={
                "source_candidates": sorted(
                    source_candidates,
                    key=lambda candidate: (candidate.priority, -candidate.source_confidence),
                )[:8],
                "queries": queries[:10],
            }
        )

    def _build_validation_profile(
        self,
        claim_text: str,
        *,
        claim: AtomicClaim | None,
    ) -> ValidationProfile:
        subject = self._central_subject(claim_text, claim=claim)
        context = self._context_hint(claim_text, claim=claim)
        terms = self._validation_terms(claim_text)

        return ValidationProfile(
            subject=subject,
            context=context,
            terms=terms,
            candidate_domains=self._candidate_domains_for_claim(
                claim_text,
                claim=claim,
                context=context,
            ),
        )

    def _central_subject(self, claim_text: str, *, claim: AtomicClaim | None) -> str:
        if claim and claim.subject and claim.object:
            return f"{claim.subject} {claim.object}".strip()
        if claim and claim.subject:
            return claim.subject

        matchup = re.search(
            r"\b([A-Z][A-Za-z']+|USA|US|U\.S\.|United States)\s+(?:beat|beats|defeated|defeats|vs\.?|versus)\s+([A-Z][A-Za-z']+|USA|US|U\.S\.|United States)\b",
            claim_text,
        )
        if matchup:
            return f"{matchup.group(1)} vs {matchup.group(2)}"

        words = re.findall(r"\b[A-Z][A-Za-z0-9']+\b|USA|U\.S\.", claim_text)
        if words:
            return " ".join(words[:4])

        return claim_text

    def _validation_terms(self, claim_text: str) -> list[str]:
        terms: list[str] = []
        lowered = claim_text.lower()

        score = re.search(r"\b\d+\s*[-–]\s*\d+\b", claim_text)
        if score:
            terms.append(f"score {score.group(0)}")

        round_match = re.search(r"\bround of \d+\b", lowered)
        if round_match:
            terms.append(round_match.group(0))

        if any(word in lowered for word in ["beat", "beats", "defeated", "defeats", "won", "lost"]):
            terms.append("match result")

        year = re.search(r"\b(?:19|20)\d{2}\b", claim_text)
        if year:
            terms.append(f"date {year.group(0)}")

        return list(dict.fromkeys(terms or ["claim verification"]))

    def _context_hint(self, claim_text: str, *, claim: AtomicClaim | None) -> str | None:
        lowered = claim_text.lower()
        explicit_year = re.search(r"\b(?:19|20)\d{2}\b", claim_text)
        current_year = explicit_year.group(0) if explicit_year else str(datetime.now(timezone.utc).year)

        if (
            claim is not None
            and claim.claim_type in {ClaimType.RESULT, ClaimType.NUMERIC, ClaimType.EVENT, ClaimType.UNKNOWN}
            and "round of 16" in lowered
            and re.search(r"\b(?:usa|us|u\.s\.|united states|belgium)\b", lowered)
        ):
            return f"{current_year} FIFA World Cup"

        if "world cup" in lowered or "worldcup" in lowered:
            return f"{current_year} FIFA World Cup" if explicit_year else "FIFA World Cup"

        return None

    def _candidate_domains_for_claim(
        self,
        claim_text: str,
        *,
        claim: AtomicClaim | None,
        context: str | None,
    ) -> list[tuple[str, SourceType, str]]:
        lowered = claim_text.lower()

        if claim is not None and claim.claim_type in {ClaimType.RESULT, ClaimType.SCHEDULE, ClaimType.NUMERIC, ClaimType.EVENT, ClaimType.UNKNOWN}:
            if "world cup" in lowered or "worldcup" in lowered or "round of 16" in lowered or (context and "World Cup" in context):
                return [
                    ("fifa.com", SourceType.OFFICIAL, "Official FIFA match and competition source."),
                    ("espn.com", SourceType.TRUSTED_MEDIA, "Trusted sports media with match reports and score pages."),
                    ("theathletic.com", SourceType.TRUSTED_MEDIA, "Trusted sports newsroom for match reports."),
                    ("soccerway.com", SourceType.DATABASE, "Structured football results database."),
                ]

            return [
                ("espn.com", SourceType.TRUSTED_MEDIA, "Trusted sports media with score coverage."),
                ("soccerway.com", SourceType.DATABASE, "Structured football results database."),
            ]

        if claim is not None and claim.claim_type == ClaimType.TRANSFER:
            return [
                ("espn.com", SourceType.TRUSTED_MEDIA, "Trusted sports media for transfer reporting."),
                ("theathletic.com", SourceType.TRUSTED_MEDIA, "Trusted sports newsroom for transfer reporting."),
            ]

        return [
            ("reuters.com", SourceType.TRUSTED_MEDIA, "Trusted general news source."),
            ("apnews.com", SourceType.TRUSTED_MEDIA, "Trusted general news source."),
            ("wikipedia.org", SourceType.AGGREGATOR, "Broad background only; should not be the sole verification source."),
        ]

    def _source_candidates_for_profile(self, profile: ValidationProfile) -> list[SourceCandidate]:
        candidates: list[SourceCandidate] = []

        for index, (domain, source_type, rationale) in enumerate(profile.candidate_domains, start=1):
            candidate = SourceCandidate(
                name=domain,
                domain=domain,
                expected_source_type=source_type,
                rationale=rationale,
                priority=index,
                validation_terms=profile.terms,
                source_confidence=0.5,
                confidence_source="planner_prior",
            )
            candidates.append(self._enrich_candidate(candidate, profile))

        return candidates

    def _queries_for_profile(
        self,
        claim_id: str,
        claim_text: str,
        profile: ValidationProfile,
    ) -> list[SearchQuery]:
        target_domains = [
            domain
            for domain, _, _ in profile.candidate_domains
        ][:3]
        context = f" {profile.context}" if profile.context else ""
        queries: list[SearchQuery] = []

        for index, term in enumerate(profile.terms, start=1):
            queries.append(
                SearchQuery(
                    query_id=f"{claim_id}_query_{index}",
                    claim_id=claim_id,
                    query=f"{profile.subject}{context} {term}".strip(),
                    purpose=f"Validate {term} against the central subject/event.",
                    cost_tier="free",
                    expected_source_type=SourceType.TRUSTED_MEDIA,
                    target_domains=target_domains,
                    provider="configured_free_provider",
                    validation_terms=[term],
                )
            )

        queries.append(
            SearchQuery(
                query_id=f"{claim_id}_query_{len(queries) + 1}",
                claim_id=claim_id,
                query=f"{claim_text} official source",
                purpose="Find a direct source while preserving the full claim context.",
                cost_tier="free",
                expected_source_type=SourceType.OFFICIAL,
                target_domains=target_domains[:1],
                provider="configured_free_provider",
                validation_terms=profile.terms,
            )
        )

        return queries

    def _is_usable_candidate(self, candidate: SourceCandidate, profile: ValidationProfile) -> bool:
        domain = self._normalize_domain(candidate.domain or candidate.url)
        if not domain or domain in {"example.com", "example.org", "example.net", "test.com", "localhost"}:
            return False

        if candidate.url and candidate.url.rstrip("/").endswith("/news/source-article"):
            return False

        if self._is_contextually_wrong_domain(domain, profile):
            return False

        return True

    def _is_usable_query(self, query: SearchQuery, profile: ValidationProfile) -> bool:
        query_text = query.query.lower().strip()
        if len(query_text.split()) < 3:
            return False

        if "nba" in query_text and profile.context and "world cup" in profile.context.lower():
            return False

        subject_tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9]+", profile.subject)
            if len(token) > 1
        }
        query_tokens = set(re.findall(r"[a-zA-Z0-9]+", query_text))

        return bool(subject_tokens.intersection(query_tokens))

    def _is_contextually_wrong_domain(self, domain: str, profile: ValidationProfile) -> bool:
        if not profile.context or "world cup" not in profile.context.lower():
            return False

        football_domains = {
            domain
            for domain, _, _ in profile.candidate_domains
        }
        allowed_general_domains = {"reuters.com", "apnews.com", "wikipedia.org"}
        wrong_sport_domains = {"nba.com", "nfl.com", "mlb.com", "nhl.com"}

        if domain in wrong_sport_domains:
            return True

        return bool(domain.endswith("nba.com") and domain not in football_domains | allowed_general_domains)

    def _enrich_candidate(self, candidate: SourceCandidate, profile: ValidationProfile) -> SourceCandidate:
        domain = self._normalize_domain(candidate.domain or candidate.url)
        if not domain:
            return candidate

        resolution = SourceReliabilityService().resolve(
            url=f"https://{domain}",
            source_id=None,
            claim_type="result",
            topic=profile.context,
            fallback=candidate.source_confidence,
        )

        return candidate.model_copy(
            update={
                "domain": domain,
                "source_confidence": resolution.reliability,
                "confidence_source": resolution.source,
                "validation_terms": candidate.validation_terms or profile.terms,
            }
        )

    def _normalize_domain(self, value: str | None) -> str | None:
        if not value:
            return None

        cleaned = value.strip().lower()
        cleaned = re.sub(r"^https?://", "", cleaned)
        cleaned = cleaned.split("/", 1)[0]
        cleaned = cleaned.removeprefix("www.")

        if "." not in cleaned:
            return None

        return cleaned
