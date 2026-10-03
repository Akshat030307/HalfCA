"""Without an LLM the pipeline still runs end to end; stage 4 is skipped."""

from __future__ import annotations

from halfca.ai import llm
from halfca.pipeline import Reconciliation


def test_no_provider_means_no_adjudicator() -> None:
    assert not llm.configured()
    assert llm.default_adjudicator() is None


def test_pipeline_without_llm(demo_no_llm: Reconciliation, demo: Reconciliation) -> None:
    s = demo_no_llm.summary
    assert s["stage4_skipped"]
    f = demo_no_llm.tables["funnel"]
    assert bool(f.skipped.iloc[-1]) and int(f.paired.iloc[-1]) == 0
    assert s["unmatched"] == 20  # the two AI-only matches stay in the queue
    # Those two are sales, so IMS and liability are untouched.
    assert s["ims"] == demo.summary["ims"]
    assert s["liability"] == demo.summary["liability"]
