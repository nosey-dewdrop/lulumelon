"""What the source layer must refuse to say, and what it may."""

from __future__ import annotations

from lulumelon.mirror.sources import MIN_PROMPTS, associate, source_graph, source_use
from lulumelon.mirror.types import Run, snapshot_from_runs

A = "https://g2.com/best-trading-agents"
B = "https://reddit.com/r/algotrading/thread"


def run(prompt_id, brands, citations):
    return Run(
        prompt_id=prompt_id,
        engine="perplexity",
        model="sonar-2026-07",
        asked_at="2026-07-31T12:00:00Z",
        brands=tuple(brands),
        citations=tuple(citations),
        surface="api",
    )


def built(spec):
    """spec: {prompt_id: [(brands, citations), ...]}"""
    runs = []
    for pid, draws in spec.items():
        for brands, cites in draws:
            runs.append(run(pid, brands, cites))
    return snapshot_from_runs("t", runs)


def test_source_use_counts_prompts_and_runs_separately():
    snap = built(
        {
            "p1": [(("Marx",), (A,)), ((), (A,)), (("Marx",), (A, B))],
            "p2": [(("Marx",), (B,)), ((), (B,)), ((), (B,))],
        }
    )
    use = {s.url: s for s in source_use(snap)}
    assert use[A].runs == 3 and use[A].prompts == 1
    assert use[B].runs == 4 and use[B].prompts == 2
    # a source cited in every run of one question is a fact about that question
    assert use[A].share_of_runs == 0.5


def test_a_source_cited_in_every_run_gets_no_contrast():
    # this is the case a competing panel prints as "0 difference, not important"
    snap = built(
        {
            "p1": [(("Marx",), (A,)), (("Marx",), (A,)), ((), (A,)), ((), (A,))],
            "p2": [(("Marx",), (A,)), ((), (A,)), ((), (A,)), ((), (A,))],
        }
    )
    got = associate(snap, "Marx", A)
    assert got.interval is None
    assert not got.is_reportable
    assert "NO CONTRAST" in got.verdict
    assert got.prompts_dropped == 2


def test_too_few_prompts_with_a_split_is_withheld():
    # one prompt splits, the rest are all-or-nothing. The difference exists but
    # the prompt is the resampling unit, so one cluster is not a population.
    snap = built(
        {
            "p1": [(("Marx",), (A,)), (("Marx",), (A,)), ((), ()), ((), ())],
            "p2": [(("Marx",), (A,)), (("Marx",), (A,)), (("Marx",), (A,)), (("Marx",), (A,))],
        }
    )
    got = associate(snap, "Marx", A)
    assert got.interval is None
    assert "WITHHELD" in got.verdict
    assert got.prompts_used < MIN_PROMPTS


def test_a_real_contrast_is_reported_but_never_called_an_effect():
    spec = {}
    for i in range(6):
        spec[f"p{i}"] = [
            (("Marx",), (A,)),
            (("Marx",), (A,)),
            (("Marx",), (A,)),
            ((), ()),
            ((), ()),
            ((), ()),
        ]
    got = associate(built(spec), "Marx", A)

    assert got.is_reportable
    assert got.rate_when_cited == 1.0
    assert got.rate_when_not == 0.0
    assert got.difference == 1.0
    # the whole point: a measurable contrast, and a refusal to call it causal
    assert "NOT EFFECT" in got.verdict
    assert "ablation" in got.verdict
    assert "effect" not in got.as_text().split("NOT EFFECT")[0]


def test_a_source_that_carries_nothing_is_said_to_carry_nothing():
    # brand appears half the time whether or not the source is cited
    spec = {}
    for i in range(6):
        spec[f"p{i}"] = [
            (("Marx",), (A,)),
            ((), (A,)),
            (("Marx",), ()),
            ((), ()),
        ]
    got = associate(built(spec), "Marx", A)
    assert got.is_reportable
    assert abs(got.difference) < 1e-9
    assert "NOT SEPARABLE FROM ZERO" in got.verdict


def test_the_graph_is_ordered_by_citation_count_not_by_effect_size():
    # B is cited far more often; A shows a bigger difference on thin evidence.
    spec = {}
    for i in range(5):
        spec[f"p{i}"] = [
            (("Marx",), (B,)),
            ((), (B,)),
            (("Marx",), (B, A)),
            ((), ()),
        ]
    graph = source_graph(built(spec), "Marx", top=2)
    assert graph[0].url == B, "ranking by effect size headlines the least stable number"


def test_the_same_round_gives_the_same_interval_twice():
    spec = {}
    for i in range(6):
        spec[f"p{i}"] = [
            (("Marx",), (A,)),
            ((), (A,)),
            (("Marx",), ()),
            ((), ()),
        ]
    snap = built(spec)
    first = associate(snap, "Marx", A, seed=11)
    second = associate(snap, "Marx", A, seed=11)
    assert first.interval == second.interval
