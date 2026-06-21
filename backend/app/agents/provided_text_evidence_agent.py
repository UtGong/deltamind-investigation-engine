import re

from pydantic import BaseModel

from app.agents.base import Agent
from app.core.constants import InputType
from app.schemas.agent import AtomicClaim, EvidenceItem


class ProvidedTextEvidenceInput(BaseModel):
    claim: AtomicClaim
    case_input_type: InputType
    case_input_text: str
    case_title: str | None = None
    source_url: str | None = None


class ProvidedTextEvidenceAgent(
    Agent[ProvidedTextEvidenceInput, list[EvidenceItem]]
):
    name = "provided_text_evidence_agent"

    def run(self, input_data: ProvidedTextEvidenceInput) -> list[EvidenceItem]:
        # A raw claim should not verify itself.
        if input_data.case_input_type == InputType.CLAIM:
            return []

        if input_data.case_input_type not in {InputType.ARTICLE_TEXT, InputType.URL}:
            return []

        matched_text = self._find_relevant_text(
            claim_text=input_data.claim.claim_text,
            source_text=input_data.case_input_text,
        )

        if matched_text is None:
            return []

        specificity = self._specificity(
            claim_text=input_data.claim.claim_text,
            evidence_text=matched_text,
        )

        source_id = (
            "source_user_provided_url"
            if input_data.case_input_type == InputType.URL
            else "source_user_provided_text"
        )

        title = input_data.case_title or (
            "User-provided URL content"
            if input_data.case_input_type == InputType.URL
            else "User-provided article/report text"
        )

        return [
            EvidenceItem(
                evidence_id=f"{input_data.claim.claim_id}_provided_text_evidence_1",
                claim_id=input_data.claim.claim_id,
                source_id=source_id,
                url=input_data.source_url,
                title=title,
                evidence_text=matched_text,
                independence_group=source_id,
                # Low by design: the source under investigation cannot strongly verify itself.
                reliability=0.35,
                independence=0.15,
                freshness=0.50,
                specificity=specificity,
            )
        ]

    def _find_relevant_text(
        self,
        claim_text: str,
        source_text: str,
    ) -> str | None:
        clean_claim = " ".join(claim_text.strip().split())
        clean_source = " ".join(source_text.strip().split())

        if not clean_claim or not clean_source:
            return None

        if clean_claim.lower() in clean_source.lower():
            return clean_claim

        sentences = self._split_sentences(source_text)
        claim_tokens = self._content_tokens(clean_claim)

        best_sentence: str | None = None
        best_overlap = 0

        for sentence in sentences:
            sentence_tokens = self._content_tokens(sentence)
            overlap = len(claim_tokens.intersection(sentence_tokens))

            if overlap > best_overlap:
                best_overlap = overlap
                best_sentence = sentence

        if best_sentence is None or best_overlap < 2:
            return None

        return best_sentence

    def _split_sentences(self, text: str) -> list[str]:
        return [
            item.strip()
            for item in re.split(r"(?<=[.!?])\s+|\n+", text)
            if item.strip()
        ]

    def _content_tokens(self, text: str) -> set[str]:
        stopwords = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "by",
            "for",
            "from",
            "has",
            "have",
            "in",
            "is",
            "it",
            "of",
            "on",
            "or",
            "that",
            "the",
            "to",
            "was",
            "were",
            "with",
        }

        tokens = {
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9]+", text)
        }

        return {token for token in tokens if token not in stopwords}

    def _specificity(self, claim_text: str, evidence_text: str) -> float:
        claim_tokens = self._content_tokens(claim_text)
        evidence_tokens = self._content_tokens(evidence_text)

        if not claim_tokens:
            return 0.4

        overlap_ratio = len(claim_tokens.intersection(evidence_tokens)) / len(claim_tokens)

        if overlap_ratio >= 0.8:
            return 0.75

        if overlap_ratio >= 0.5:
            return 0.60

        return 0.45
