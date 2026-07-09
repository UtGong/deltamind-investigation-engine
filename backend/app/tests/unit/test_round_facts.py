from app.agents.round_facts import (
    build_round_correction,
    extract_round_fact,
    infer_round_stance,
)


def test_infer_round_stance_contradicts_different_round_values():
    stance = infer_round_stance(
        claim_text="The match took place in the Round of 9.",
        evidence_text="USA loses 4-1 in World Cup round of 16 against Belgium.",
    )

    assert stance == "contradicts"


def test_infer_round_stance_supports_same_round_values():
    stance = infer_round_stance(
        claim_text="The match took place in the Round of 16.",
        evidence_text="USA loses 4-1 in World Cup round of 16 against Belgium.",
    )

    assert stance == "supports"


def test_build_round_correction_replaces_only_the_round_value():
    correction = build_round_correction(
        claim_text="Belgium beats USA with a 4-1 win in the Round of 9 in Worldcup 2026",
        evidence_texts=[
            "USA loses 4-1 in World Cup round of 16 against Belgium, ending the run."
        ],
    )

    assert correction == (
        "Belgium beats USA with a 4-1 win in the Round of 16 in Worldcup 2026",
        "Round of 9",
        "Round of 16",
    )


def test_extract_round_fact_returns_none_when_no_round_claim_exists():
    assert extract_round_fact("Belgium beats USA 4-1.") is None
