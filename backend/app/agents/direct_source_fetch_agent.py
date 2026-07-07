from urllib.parse import quote_plus, urlparse

from pydantic import BaseModel, Field

from app.agents.base import Agent
from app.agents.url_fetch_agent import UrlFetchAgent, UrlFetchInput
from app.core.constants import SourceType
from app.schemas.agent import AtomicClaim
from app.schemas.search import SearchPlan, SearchQuery, SearchResult, SourceCandidate


class DirectSourceFetchInput(BaseModel):
    claim: AtomicClaim
    search_plan: SearchPlan


class DirectSourceFetchOutput(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    skipped_candidates: list[str] = Field(default_factory=list)
    expanded_urls: list[str] = Field(default_factory=list)
    failed_urls: list[str] = Field(default_factory=list)


class DirectSourceFetchAgent(
    Agent[DirectSourceFetchInput, DirectSourceFetchOutput]
):
    name = "direct_source_fetch_agent"

    def __init__(
        self,
        url_fetch_agent: UrlFetchAgent | None = None,
        max_snippet_chars: int = 2500,
        max_expanded_urls_per_candidate: int = 4,
        max_total_fetches: int = 12,
    ) -> None:
        self.url_fetch_agent = url_fetch_agent or UrlFetchAgent()
        self.max_snippet_chars = max_snippet_chars
        self.max_expanded_urls_per_candidate = max_expanded_urls_per_candidate
        self.max_total_fetches = max_total_fetches

    def run(self, input_data: DirectSourceFetchInput) -> DirectSourceFetchOutput:
        results: list[SearchResult] = []
        skipped_candidates: list[str] = []
        expanded_urls: list[str] = []
        failed_urls: list[str] = []

        seen_urls: set[str] = set()
        fetch_count = 0

        for candidate_index, candidate in enumerate(
            sorted(input_data.search_plan.source_candidates, key=lambda item: item.priority),
            start=1,
        ):
            candidate_urls = self._candidate_urls(
                claim=input_data.claim,
                candidate=candidate,
                search_plan=input_data.search_plan,
            )

            if not candidate_urls:
                skipped_candidates.append(
                    candidate.domain or candidate.name or f"candidate_{candidate_index}"
                )
                continue

            expanded_urls.extend(url for url in candidate_urls if url != candidate.url)

            for url_index, url in enumerate(candidate_urls, start=1):
                if fetch_count >= self.max_total_fetches:
                    skipped_candidates.append(
                        f"fetch_budget_exhausted_after_{self.max_total_fetches}"
                    )
                    break

                normalized_url = self._normalize_url_for_dedupe(url)
                if normalized_url in seen_urls:
                    continue

                seen_urls.add(normalized_url)
                fetch_count += 1

                try:
                    fetched = self.url_fetch_agent.run(UrlFetchInput(url=url))
                except Exception:
                    failed_urls.append(url)
                    skipped_candidates.append(url)
                    continue

                if fetched.error or not fetched.text:
                    failed_urls.append(url)
                    skipped_candidates.append(url)
                    continue

                results.append(
                    self._to_search_result(
                        claim=input_data.claim,
                        candidate=candidate,
                        result_suffix=f"{candidate_index}_{url_index}",
                        final_url=fetched.final_url or url,
                        title=fetched.title or candidate.name or url,
                        text=fetched.text,
                    )
                )

        return DirectSourceFetchOutput(
            results=results,
            skipped_candidates=skipped_candidates,
            expanded_urls=expanded_urls,
            failed_urls=failed_urls,
        )

    def _candidate_urls(
        self,
        claim: AtomicClaim,
        candidate: SourceCandidate,
        search_plan: SearchPlan,
    ) -> list[str]:
        if candidate.url:
            return [candidate.url]

        domain = self._normalize_domain(candidate.domain)
        if not domain or not search_plan.queries:
            return []

        urls: list[str] = []
        for query in self._queries_for_domain(claim=claim, domain=domain, search_plan=search_plan):
            urls.extend(self._domain_search_urls(domain, query))

        deduped: list[str] = []
        seen: set[str] = set()
        for url in urls:
            normalized = self._normalize_url_for_dedupe(url)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(url)
            if len(deduped) >= self.max_expanded_urls_per_candidate:
                break

        return deduped

    def _queries_for_domain(
        self,
        claim: AtomicClaim,
        domain: str,
        search_plan: SearchPlan,
    ) -> list[str]:
        matching_queries: list[SearchQuery] = []

        for query in search_plan.queries:
            target_domains = [
                self._normalize_domain(target_domain)
                for target_domain in query.target_domains
            ]

            if not target_domains:
                continue

            if domain in target_domains or any(
                target_domain and (target_domain.endswith(domain) or domain.endswith(target_domain))
                for target_domain in target_domains
            ):
                matching_queries.append(query)

        if not matching_queries:
            matching_queries = search_plan.queries

        query_texts = [query.query.strip() for query in matching_queries if query.query.strip()]

        if not query_texts:
            query_texts = [claim.claim_text]

        deduped: list[str] = []
        seen: set[str] = set()

        for query_text in query_texts:
            key = query_text.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(query_text)
            if len(deduped) >= 2:
                break

        return deduped

    def _domain_search_urls(self, domain: str, query: str) -> list[str]:
        encoded_query = quote_plus(query)
        return [
            f"https://{domain}/search?q={encoded_query}",
            f"https://{domain}/?s={encoded_query}",
        ]

    def _to_search_result(
        self,
        claim: AtomicClaim,
        candidate: SourceCandidate,
        result_suffix: str,
        final_url: str,
        title: str,
        text: str,
    ) -> SearchResult:
        domain = candidate.domain or self._extract_domain(final_url)

        return SearchResult(
            result_id=f"{claim.claim_id}_direct_source_result_{result_suffix}",
            query_id=f"{claim.claim_id}_direct_source_fetch_{result_suffix}",
            title=title,
            url=final_url,
            snippet=text[: self.max_snippet_chars],
            source_name=candidate.name or domain,
            domain=self._normalize_domain(domain),
            source_type=SourceType.UNKNOWN,
            reliability=0.5,
            independence=0.7,
            freshness=0.6,
            specificity=0.7,
        )

    def _extract_domain(self, url: str) -> str:
        parsed = urlparse(url.strip())
        if parsed.netloc:
            return parsed.netloc.removeprefix("www.").lower()

        cleaned = url.strip().lower()
        cleaned = cleaned.removeprefix("https://").removeprefix("http://")
        return cleaned.split("/", 1)[0].removeprefix("www.") or "unknown"

    def _normalize_domain(self, domain: str | None) -> str | None:
        if not domain:
            return None

        cleaned = domain.strip().lower()
        cleaned = cleaned.removeprefix("https://").removeprefix("http://")
        cleaned = cleaned.split("/", 1)[0]
        cleaned = cleaned.removeprefix("www.")

        return cleaned or None

    def _normalize_url_for_dedupe(self, url: str) -> str:
        return url.strip().rstrip("/")
