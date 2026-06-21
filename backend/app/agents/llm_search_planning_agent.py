import json
import re

from pydantic import BaseModel

from app.agents.base import Agent
from app.core.config import get_settings
from app.core.constants import SourceType
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
                        "10. Do not use provider names like mock unless the user explicitly asks for mock mode.\n\n"
                        "Good source_candidate examples:\n"
                        "{\n"
                        '  "name": "NBA official news article",\n'
                        '  "domain": "nba.com",\n'
                        '  "url": "https://www.nba.com/news/boston-celtics-win-2024-nba-finals",\n'
                        '  "expected_source_type": "official",\n'
                        '  "rationale": "Official league article likely containing the result.",\n'
                        '  "priority": 1\n'
                        "}\n\n"
                        "If you only know the domain, do this:\n"
                        "{\n"
                        '  "name": "NBA official website",\n'
                        '  "domain": "nba.com",\n'
                        '  "url": null,\n'
                        '  "expected_source_type": "official",\n'
                        '  "rationale": "Official league source, but exact article URL is not known.",\n'
                        '  "priority": 1\n'
                        "}\n\n"
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
                        '      "target_domains": ["nba.com"],\n'
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
        content: str,
    ) -> SearchPlan:
        payload = self._safe_json_loads(content)

        if payload is None or not isinstance(payload, dict):
            return self._fallback_plan(claim_id, claim_text)

        source_candidates = self._parse_source_candidates(
            payload.get("source_candidates", [])
        )
        queries = self._parse_queries(
            claim_id=claim_id,
            raw_queries=payload.get("queries", []),
        )

        should_use_paid_search = bool(payload.get("should_use_paid_search", False))
        max_paid_search_calls = self._parse_nonnegative_int(
            payload.get("max_paid_search_calls"),
            default=0,
        )

        return SearchPlan(
            claim_id=claim_id,
            source_candidates=source_candidates,
            queries=queries,
            should_use_paid_search=should_use_paid_search,
            paid_search_rationale=payload.get("paid_search_rationale"),
            max_paid_search_calls=max_paid_search_calls,
        )

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

    def _fallback_plan(self, claim_id: str, claim_text: str) -> SearchPlan:
        return SearchPlan(
            claim_id=claim_id,
            source_candidates=[],
            queries=[
                SearchQuery(
                    query_id=f"{claim_id}_query_1",
                    claim_id=claim_id,
                    query=f"{claim_text} official source",
                    purpose="Fallback free query for a primary or official source.",
                    cost_tier="free",
                    expected_source_type=SourceType.UNKNOWN,
                    provider="configured_free_provider",
                ),
                SearchQuery(
                    query_id=f"{claim_id}_query_2",
                    claim_id=claim_id,
                    query=f"{claim_text} independent report",
                    purpose="Fallback free query for independent corroboration.",
                    cost_tier="free",
                    expected_source_type=SourceType.UNKNOWN,
                    provider="configured_free_provider",
                ),
            ],
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

    def _parse_nonnegative_int(self, value: object, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default

        return max(0, parsed)

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
