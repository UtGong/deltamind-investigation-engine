from app.agents.provided_text_evidence_agent import (
    ProvidedTextEvidenceAgent,
    ProvidedTextEvidenceInput,
)
from app.core.constants import ClaimType, InputType
from app.schemas.agent import AtomicClaim


def test_provided_text_evidence_agent_extracts_from_article_text():
    agent = ProvidedTextEvidenceAgent()

    claim = AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final 3-1.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )

    output = agent.run(
        ProvidedTextEvidenceInput(
            claim=claim,
            case_input_type=InputType.ARTICLE_TEXT,
            case_input_text=(
                "Player X joined Club A on June 10. "
                "Team A won the final 3-1. "
                "Player Y is injured."
            ),
            case_title="Provided article",
        )
    )

    assert len(output) == 1
    assert output[0].source_id == "source_user_provided_text"
    assert output[0].evidence_text == "Team A won the final 3-1."
    assert output[0].reliability == 0.35
    assert output[0].independence == 0.15


def test_provided_text_evidence_agent_extracts_from_fetched_url_text():
    agent = ProvidedTextEvidenceAgent()

    claim = AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final 3-1.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )

    output = agent.run(
        ProvidedTextEvidenceInput(
            claim=claim,
            case_input_type=InputType.URL,
            case_input_text="The report says Team A won the final 3-1.",
            case_title="Fetched URL article",
            source_url="https://example.com/article",
        )
    )

    assert len(output) == 1
    assert output[0].source_id == "source_user_provided_url"
    assert output[0].url == "https://example.com/article"


def test_provided_text_evidence_agent_does_not_self_verify_raw_claim():
    agent = ProvidedTextEvidenceAgent()

    claim = AtomicClaim(
        claim_id="claim_1",
        claim_text="Team A won the final 3-1.",
        claim_type=ClaimType.RESULT,
        confidence=0.9,
    )

    output = agent.run(
        ProvidedTextEvidenceInput(
            claim=claim,
            case_input_type=InputType.CLAIM,
            case_input_text="Team A won the final 3-1.",
            case_title="Raw claim",
        )
    )

    assert output == []
