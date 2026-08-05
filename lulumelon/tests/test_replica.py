"""The instrument, stated as the ways it could quietly measure the wrong thing.

A replica is the only apparatus here that manufactures its own conditions, so
almost every failure it can have is silent: an arm that ablated nothing, a
treatment that changed halfway through, a laboratory answer that reached the
ledger wearing a live label. None of those raise on their own, and each one
produces a clean number with a wrong meaning attached, which is worse than a
crash by exactly the amount a customer trusts the screen.
"""

from __future__ import annotations

import pytest

from lulumelon.collect import (
    INSTRUCTION_VERSION,
    REPLICA_SURFACE,
    SURFACES,
    FakeProvider,
    Ledger,
    Prompt,
    ReplicaProvider,
    Usage,
    is_replica_surface,
    replay,
    replica_prompt,
    replica_surface,
    run_round,
    source_fingerprint,
    without,
)
from lulumelon.collect.detect import Brand

SOURCES = ("https://a.example/guide", "https://b.example/list", "https://c.example/review")


def brands() -> tuple[Brand, ...]:
    return (Brand(name="ornek", aliases=()),)


# -- the prompt is the experiment -------------------------------------------


def test_the_sources_are_supplied_in_the_order_they_were_given():
    """Position in a supplied list is a treatment, so it is never reordered."""
    text = replica_prompt("who should I use?", SOURCES)
    positions = [text.index(url) for url in SOURCES]
    assert positions == sorted(positions)
    assert "[1] https://a.example/guide" in text
    assert "[3] https://c.example/review" in text


def test_the_question_survives_the_wrapping_verbatim():
    text = replica_prompt("  who should I use?  ", SOURCES)
    assert text.endswith("Question: who should I use?")


def test_the_wording_supplies_material_without_telling_the_model_to_use_it():
    """An instruction to answer from the sources manufactures the finding."""
    text = replica_prompt("who should I use?", SOURCES).lower()
    for manufactured in ("based on", "using these", "prefer", "according to the sources"):
        assert manufactured not in text


def test_a_replica_with_no_sources_is_refused_by_name():
    with pytest.raises(ValueError, match="not a replica"):
        replica_prompt("who should I use?", ())


def test_a_replica_with_no_question_is_refused():
    with pytest.raises(ValueError, match="needs a question"):
        replica_prompt("   ", SOURCES)


# -- an ablation that removes nothing is the dangerous one ------------------


def test_removing_a_source_removes_exactly_that_source():
    assert without(SOURCES, SOURCES[1]) == (SOURCES[0], SOURCES[2])


def test_removing_a_source_that_was_never_there_is_refused():
    """Two identical arms produce a difference of zero and a false conclusion."""
    with pytest.raises(ValueError, match="changes nothing"):
        without(SOURCES, "https://d.example/not-in-the-list")


def test_the_other_arm_differs_in_one_source_and_nothing_else():
    full = ReplicaProvider(base=FakeProvider(), sources=SOURCES)
    dropped = full.dropping(SOURCES[1])

    assert set(full.sources) - set(dropped.sources) == {SOURCES[1]}
    assert full.instruction_version == dropped.instruction_version
    assert full.name == dropped.name


def test_the_two_arms_do_not_share_a_label():
    """They are both laboratory rounds and they are not the same condition.

    Filing them under one surface would leave two treatments indistinguishable
    once they are on disk, and an ablation whose arms cannot be told apart
    afterwards is a result nobody can check, including us.
    """
    full = ReplicaProvider(base=FakeProvider(), sources=SOURCES)
    dropped = full.dropping(SOURCES[1])

    assert full.surface != dropped.surface
    assert is_replica_surface(full.surface) and is_replica_surface(dropped.surface)
    assert full.surface == replica_surface(SOURCES)
    assert dropped.surface == replica_surface(without(SOURCES, SOURCES[1]))


def test_a_repeated_source_is_refused_because_it_is_an_unchosen_treatment():
    with pytest.raises(ValueError, match="supplied twice"):
        ReplicaProvider(base=FakeProvider(), sources=(*SOURCES, SOURCES[0]))


def test_a_replica_provider_without_sources_is_refused():
    with pytest.raises(ValueError, match="needs the sources"):
        ReplicaProvider(base=FakeProvider(), sources=())


# -- a laboratory answer must never wear a live label -----------------------


def test_the_answer_comes_back_labelled_as_a_replica_whatever_the_base_says():
    base = FakeProvider(surface="api")
    answer = ReplicaProvider(base=base, sources=SOURCES).ask("who should I use?")
    assert is_replica_surface(answer.surface)
    assert answer.surface != "api"
    assert base.surface == "api", "the base provider is not mutated"


def test_the_replica_surface_is_a_declared_surface():
    """Anything outside `SURFACES` is a provider bug, including ours."""
    assert REPLICA_SURFACE in SURFACES
    assert ReplicaProvider(base=FakeProvider(), sources=SOURCES).surface.startswith(
        f"{REPLICA_SURFACE}-"
    )


def test_a_surface_cannot_be_handed_to_a_replica():
    """A label that can be passed in is a label that can be passed in wrong."""
    with pytest.raises(TypeError):
        ReplicaProvider(base=FakeProvider(), sources=SOURCES, surface="api")


def test_a_replica_round_reaches_the_ledger_under_its_own_surface(tmp_path):
    provider = ReplicaProvider(
        base=FakeProvider(script={}, usage=Usage(input_tokens=120, output_tokens=70)),
        sources=SOURCES,
    )
    ledger = Ledger(tmp_path)
    result = run_round(
        ledger=ledger,
        provider=provider,
        prompts=[Prompt(id="p1", text="who should I use?")],
        brands=brands(),
        k=2,
        subject="ornek",
    )
    assert REPLICA_SURFACE in result.snapshot_id
    asks = [r for r in ledger.read(result.snapshot_id) if not r.is_seal]
    assert {r.surface for r in asks} == {replica_surface(SOURCES)}
    assert ledger.verify(result.snapshot_id) == []


def test_a_replica_round_is_never_a_single_condition_with_a_live_one(tmp_path):
    """Pooling the two would report a laboratory rate as what a user sees."""
    ledger = Ledger(tmp_path)
    prompts = [Prompt(id="p1", text="who should I use?")]

    live = run_round(
        ledger=ledger, provider=FakeProvider(surface="api"), prompts=prompts,
        brands=brands(), k=2, subject="ornek",
    )
    lab = run_round(
        ledger=ledger,
        provider=ReplicaProvider(base=FakeProvider(surface="api"), sources=SOURCES),
        prompts=prompts, brands=brands(), k=2, subject="ornek",
    )
    mixed = replay(ledger, live.snapshot_id).runs + replay(ledger, lab.snapshot_id).runs
    assert len({r.surface for r in mixed}) == 2


# -- the treatment is on disk, not on the command line ----------------------


def test_the_order_of_the_list_is_inside_the_fingerprint():
    """Position in a supplied list is a treatment, so a reorder is a new arm."""
    assert source_fingerprint(SOURCES) != source_fingerprint(tuple(reversed(SOURCES)))


def test_removing_a_source_changes_the_fingerprint():
    assert source_fingerprint(SOURCES) != source_fingerprint(without(SOURCES, SOURCES[1]))


def test_the_same_list_fingerprints_the_same_way_every_time():
    assert source_fingerprint(SOURCES) == source_fingerprint(list(SOURCES))


def test_an_edited_instruction_changes_the_fingerprint_without_anyone_bumping_a_version():
    """The version asks a person to remember. This does not need them to."""
    edited = source_fingerprint(SOURCES, instruction="{sources}\n\nQuestion: {question}!")
    assert edited != source_fingerprint(SOURCES)


def test_a_bumped_version_changes_the_fingerprint_too():
    assert source_fingerprint(SOURCES, instruction_version=2) != source_fingerprint(SOURCES)


def test_a_round_written_before_digests_is_readable_and_not_verifiable():
    assert is_replica_surface(REPLICA_SURFACE)
    assert is_replica_surface(replica_surface(SOURCES))
    assert not is_replica_surface("api")
    assert not is_replica_surface("replicant")


def test_the_fingerprint_does_not_carry_the_customers_list():
    """One-way, so the ledger proves which list was used without storing it."""
    surface = replica_surface(SOURCES)
    for url in SOURCES:
        assert url not in surface
    assert len(surface.rsplit("-", 1)[1]) == 12


# -- the instrument is versioned so two rounds can be told apart ------------


def test_the_instrument_carries_a_version_a_round_can_be_traced_to():
    assert ReplicaProvider(base=FakeProvider(), sources=SOURCES).instruction_version == (
        INSTRUCTION_VERSION
    )


def test_the_same_question_and_sources_produce_the_same_prompt_every_time():
    """A replica whose prompt drifts is two experiments sharing a name."""
    assert replica_prompt("who?", SOURCES) == replica_prompt("who?", SOURCES)


# -- the whole path runs with no key and no network -------------------------


def test_both_arms_can_be_collected_end_to_end_against_the_stub(tmp_path):
    question = "who should I use?"
    full = ReplicaProvider(base=FakeProvider(), sources=SOURCES)
    dropped = full.dropping(SOURCES[1])

    # The stub is keyed on the exact prompt, which is how the two arms are made
    # to answer differently here: with the source present the brand is named.
    full.base.script = {replica_prompt(question, full.sources): ("ornek is the usual pick.",)}
    dropped.base = FakeProvider(
        script={replica_prompt(question, dropped.sources): ("nobody in particular.",)}
    )

    ledger = Ledger(tmp_path)
    prompts = [Prompt(id="p1", text=question)]
    with_source = run_round(
        ledger=ledger, provider=full, prompts=prompts, brands=brands(), k=3, subject="ornek"
    )
    without_source = run_round(
        ledger=ledger, provider=dropped, prompts=prompts, brands=brands(), k=3, subject="ornek"
    )

    assert with_source.errors == 0 and without_source.errors == 0
    named = [r.brands for r in ledger.read(with_source.snapshot_id) if not r.is_seal]
    unnamed = [r.brands for r in ledger.read(without_source.snapshot_id) if not r.is_seal]
    assert named == [("ornek",)] * 3
    assert unnamed == [()] * 3
