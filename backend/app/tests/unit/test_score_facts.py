from app.agents.score_facts import build_score_correction, infer_score_stance


def test_score_stance_understands_team_score_team_titles():
    stance = infer_score_stance(
        claim_text="Belgium beats USA with a 3-1 win in the Round of 16",
        evidence_text=(
            "USA 1-4 Belgium | Result, Stats & Highlights | Round of 16 | "
            "FIFA World Cup 2026"
        ),
    )

    assert stance == "contradicts"


def test_score_stance_understands_lost_to_with_win_wording():
    stance = infer_score_stance(
        claim_text="USA lost to Belgium with a 3-1 win",
        evidence_text="USA 1-4 Belgium | Result, Stats & Highlights | Round of 16",
    )

    assert stance == "contradicts"


def test_score_correction_uses_team_score_team_titles():
    correction = build_score_correction(
        claim_text="Belgium beats USA with a 3-1 win in the Round of 16",
        evidence_texts=[
            "USA 1-4 Belgium | Result, Stats & Highlights | Round of 16 | FIFA"
        ],
    )

    assert correction == (
        "Belgium beats USA with a 4-1 win in the Round of 16",
        "3-1",
        "4-1",
    )
