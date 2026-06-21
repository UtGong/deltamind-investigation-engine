from app.agents.llm_stance_agent import LLMStanceAgent, LLMStanceInput
from app.core.constants import ClaimType, StanceLabel
from app.providers.llm.dev_deterministic_provider import DevDeterministicLLMProvider
from app.schemas.agent import AtomicClaim, EvidenceItem


def test_llm_stance_agent_parses_dev_deterministic_supports_response():
    agent = LLMStanceAgent(llm_provider=DevDeterministicLLMProvider())

    claim = AtomicClaim(
        claim_id="C1",
        claim_text="The Boston Celtics won the 2024 NBA Finals.",
        claim_type=ClaimType.EVENT,
        subject="The Boston Celtics",
        predicate="won",
        object="the 2024 NBA Finals",
        confidence=1.0,
    )

    evidence = EvidenceItem(
        evidence_id="E1",
        claim_id="C1",
        source_id="S1",
        title="2024 NBA Finals | NBA.com",
        evidence_text=(
            "The Boston Celtics defeated the Dallas Mavericks and won "
            "the 2024 NBA Finals championship."
        ),
        reliability=0.95,
        specificity=0.9,
        independence=0.7,
        freshness=0.7,
    )

    output = agent.run(
        LLMStanceInput(
            claim=claim,
            evidence=evidence,
        )
    )

    assert output.stance.stance == StanceLabel.SUPPORTS
    assert output.stance.confidence >= 0.9


def test_llm_stance_agent_contradicts_mavericks_winner_claim():
    agent = LLMStanceAgent(llm_provider=DevDeterministicLLMProvider())

    claim = AtomicClaim(
        claim_id="C1",
        claim_text="The Dallas Mavericks won the 2024 NBA Finals.",
        claim_type=ClaimType.EVENT,
        subject="The Dallas Mavericks",
        predicate="won",
        object="the 2024 NBA Finals",
        confidence=1.0,
    )

    evidence = EvidenceItem(
        evidence_id="E1",
        claim_id="C1",
        source_id="S1",
        title="2024 NBA Finals | NBA.com",
        evidence_text=(
            "NBA FINALS: CELTICS VS. MAVERICKS. Chasing History: "
            "Celtics clinch banner 18. Jayson Tatum and Finals MVP "
            "Jaylen Brown close out Dallas in Game 5 to secure Boston's "
            "NBA-record 18th championship."
        ),
        reliability=0.95,
        specificity=0.9,
        independence=0.7,
        freshness=0.7,
    )

    output = agent.run(
        LLMStanceInput(
            claim=claim,
            evidence=evidence,
        )
    )

    assert output.stance.stance == StanceLabel.CONTRADICTS
    assert output.stance.confidence >= 0.9


def test_llm_stance_agent_treats_search_result_page_as_insufficient():
    agent = LLMStanceAgent(llm_provider=DevDeterministicLLMProvider())

    claim = AtomicClaim(
        claim_id="C1",
        claim_text="The Dallas Mavericks won the 2024 NBA Finals.",
        claim_type=ClaimType.EVENT,
        subject="The Dallas Mavericks",
        predicate="won",
        object="the 2024 NBA Finals",
        confidence=1.0,
    )

    evidence = EvidenceItem(
        evidence_id="E1",
        claim_id="C1",
        source_id="S1",
        title="Dallas Mavericks won 2024 NBA Finals - ESPN Search",
        evidence_text=(
            "Search Found results for "
            "\"Dallas Mavericks won 2024 NBA Finals\". "
            "Terms of Use Privacy Policy."
        ),
        reliability=0.78,
        specificity=0.7,
        independence=0.7,
        freshness=0.6,
    )

    output = agent.run(
        LLMStanceInput(
            claim=claim,
            evidence=evidence,
        )
    )

    assert output.stance.stance == StanceLabel.INSUFFICIENT
