"""S3-HF-09 — corpus regression gate.

Walks scripts/chaos/corpus/ and scores every fixture through rca_scorer.
Each fixture carries a `_corpus_meta` block declaring the expected grade
(A / B / C / F) — the test fails if the actual grade is BETTER than
expected (regression: we used to catch this RCA as bad; now we don't).

This is the CI guard. If anyone weakens an axis — relaxes a regex,
widens an archetype vocab too aggressively, drops the archetype-match
gate — the 0b215ef3 corpus entry stops failing axis 5 and the test
fails. That's the entire point: prevent silent quality regressions.

Run from the monitoring-project repo root:
    cd scripts/chaos && python -m pytest test_corpus_regression.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.rca_scorer import score_rca

CORPUS_DIR = Path(__file__).parent / "corpus"
_GRADE_RANK = {"F": 0, "C": 1, "B": 2, "A": 3}


def _all_fixtures() -> list[Path]:
    return sorted([p for p in CORPUS_DIR.rglob("*.json") if p.is_file()])


@pytest.mark.parametrize("fixture", _all_fixtures(), ids=lambda p: str(p.relative_to(CORPUS_DIR)))
def test_corpus_fixture_grades(fixture: Path):
    """Every corpus fixture must score AT WORST its declared expected grade.

    `expected_grade=F` means "the scorer MUST rate this F" — if it rates
    higher (C / B / A), a regression has happened. `expected_grade=A`
    means "must rate A" — if it drops, the scorer has become too strict
    on good RCAs.
    """
    payload = json.loads(fixture.read_text())
    meta = payload.get("_corpus_meta") or {}
    expected = meta.get("expected_grade")
    assert expected in _GRADE_RANK, (
        f"{fixture.name}: invalid or missing expected_grade ({expected!r})"
    )

    score = score_rca(payload)
    actual = score.grade

    # The contract is strict-equality. "F means F" — if the corpus entry
    # is a known-bad and now scores anything other than F, the scorer
    # has weakened. Same for known-good A entries.
    assert actual == expected, (
        f"{fixture.name}: expected grade {expected}, got {actual} "
        f"(total={score.total:.2f}). Axes: lede={score.cause_first_lede} "
        f"named={score.named_cause} evidence={score.specific_evidence} "
        f"action={score.state_changing_action} archetype={score.archetype_match}. "
        f"Notes: {score.notes}"
    )

    # Optional per-axis constraints in the corpus_meta — used to pin the
    # specific axis that catches a known-bad entry. For 0b215ef3, the
    # archetype_match axis MUST score 0.0 — if anything else relaxes it,
    # the firewall is broken and we want a loud failure.
    if "min_archetype_match" in meta:
        assert score.archetype_match >= meta["min_archetype_match"], (
            f"{fixture.name}: archetype_match={score.archetype_match} "
            f"below min={meta['min_archetype_match']}"
        )
    if "max_archetype_match" in meta:
        assert score.archetype_match <= meta["max_archetype_match"], (
            f"{fixture.name}: archetype_match={score.archetype_match} "
            f"above max={meta['max_archetype_match']} — the scorer used to "
            f"catch this RCA as wrong-archetype but now passes it"
        )


def test_corpus_has_a_known_bad_seed():
    """Sanity: the corpus must contain at least one expected-F entry, or
    the regression gate is toothless."""
    fixtures = _all_fixtures()
    bad = []
    for p in fixtures:
        meta = (json.loads(p.read_text()).get("_corpus_meta") or {})
        if meta.get("expected_grade") == "F":
            bad.append(p)
    assert bad, "Corpus has no expected_grade=F fixtures — the regression gate is toothless"


def test_corpus_has_known_good_seeds():
    """Sanity: must contain expected-A entries so we catch over-strict regressions too."""
    fixtures = _all_fixtures()
    good = []
    for p in fixtures:
        meta = (json.loads(p.read_text()).get("_corpus_meta") or {})
        if meta.get("expected_grade") == "A":
            good.append(p)
    assert good, "Corpus has no expected_grade=A fixtures — can't detect over-strict regressions"
