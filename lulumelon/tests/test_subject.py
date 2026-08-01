"""The one input a person writes by hand, stated as the rounds it must refuse.

Two things in a subject file cannot be recovered once a round has been
collected against it. Which strings count as a mention is one: `detect` matches
declared literals, so an alias nobody wrote is a mention that never happened.
The prompt ids are the other, and they are worse, because a file that loads
with the wrong ones produces a round that is readable, priceable and paired
against the wrong questions in every comparison anybody ever runs on it.

So every test here is a file that would have produced a plausible round with
nothing in it, and the money spent before anybody could tell.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lulumelon.collect import SubjectFileError, load_subject

#: The file this repo actually ships, read rather than imitated. A loader
#: tested only against fixtures it wrote itself is a loader that agrees with
#: itself.
SHIPPED = Path(__file__).resolve().parents[2] / "data" / "subjects" / "marx.json"

VALID = {
    "subject": {
        "id": "marx",
        "name": "Marx",
        "domain": "marx.finance",
        "aliases": ["Marx Finance", "marx.finance"],
        "ambiguousName": True,
    },
    "projects": [],
    "competitors": [],
    "prompts": [
        {"id": "m1", "text": "What is marx.finance?", "intent": "entity", "axis": "brand"},
        {"id": "m2", "text": "Agentic finance platforms in 2026"},
    ],
}


def written(tmp_path: Path, doc: dict, name: str = "subject.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def altered(**over) -> dict:
    doc = json.loads(json.dumps(VALID))
    doc.update(over)
    return doc


# -- the file this repo ships ------------------------------------------------


def test_the_subject_file_in_this_repo_loads_as_the_round_it_describes():
    subject = load_subject(SHIPPED)

    assert subject.id == "marx"
    assert subject.name == "Marx"
    assert subject.ambiguous_name is True
    assert [p.id for p in subject.prompts] == [f"m{i}" for i in range(1, 11)]
    assert subject.prompts[0].text == "What is marx.finance?"
    assert subject.brands[0].forms == ("Marx Finance", "marx.finance", "Marx")
    assert subject.competitors == (), "the file lists none, and none are invented"


def test_the_aliases_are_taken_exactly_as_written(tmp_path):
    """Nothing is folded in, not even the domain in the field next door.

    What counts as a mention is the author's declaration. A loader that widened
    it would change the number without changing the file the number is supposed
    to be reproducible from.
    """
    doc = altered()
    doc["subject"]["aliases"] = ["Marx Finance"]
    subject = load_subject(written(tmp_path, doc))

    assert subject.brands[0].aliases == ("Marx Finance",)
    assert "marx.finance" not in subject.brands[0].forms


# -- a round that could not mean anything ------------------------------------


def test_a_file_with_no_prompts_is_refused(tmp_path):
    with pytest.raises(SubjectFileError, match="asks nothing and measures nothing"):
        load_subject(written(tmp_path, altered(prompts=[])))


def test_two_prompts_under_one_id_are_refused_rather_than_renumbered(tmp_path):
    """The refusal that matters most, because the alternative is silent.

    Renumbered, the file loads, the round runs, and every comparison against it
    pairs one question with another. Nothing on screen disagrees, because both
    sides have the same number of prompts.
    """
    doc = altered()
    doc["prompts"][1]["id"] = "m1"

    with pytest.raises(SubjectFileError, match="permanent identity") as refused:
        load_subject(written(tmp_path, doc))
    assert "prompts[1]" in str(refused.value) and "prompts[0]" in str(refused.value)


def test_a_prompt_with_no_id_is_refused(tmp_path):
    doc = altered()
    del doc["prompts"][0]["id"]

    with pytest.raises(SubjectFileError, match=r"prompts\[0\] is missing \['id'\]"):
        load_subject(written(tmp_path, doc))


def test_a_prompt_with_no_text_is_refused(tmp_path):
    doc = altered()
    doc["prompts"][0]["text"] = "   "

    with pytest.raises(SubjectFileError, match="has to be a string with something in it"):
        load_subject(written(tmp_path, doc))


def test_a_brand_with_no_name_is_refused(tmp_path):
    doc = altered()
    doc["subject"]["name"] = ""

    with pytest.raises(SubjectFileError, match="subject.name"):
        load_subject(written(tmp_path, doc))


def test_a_competitor_with_no_name_is_refused(tmp_path):
    with pytest.raises(SubjectFileError, match=r"competitors\[0\] is missing \['name'\]"):
        load_subject(written(tmp_path, altered(competitors=[{"aliases": ["r.example"]}])))


def test_a_blank_alias_is_refused(tmp_path):
    doc = altered()
    doc["subject"]["aliases"] = ["Marx Finance", " "]

    with pytest.raises(SubjectFileError, match=r"aliases\[1\]"):
        load_subject(written(tmp_path, doc))


def test_two_tracked_names_that_are_the_same_name_are_refused(tmp_path):
    """One line per name is reported, so the second would never appear."""
    doc = altered(competitors=[{"name": "marx", "aliases": []}])

    with pytest.raises(SubjectFileError, match="silently unmeasured"):
        load_subject(written(tmp_path, doc))


def test_a_competitor_is_tracked_beside_the_subject(tmp_path):
    doc = altered(
        competitors=[{"name": "Numerai", "aliases": ["numer.ai"]}],
        projects=[{"name": "Marx Signals"}],
    )
    subject = load_subject(written(tmp_path, doc))

    assert [b.name for b in subject.brands] == ["Marx", "Marx Signals", "Numerai"]
    assert subject.competitors[1].aliases == ("numer.ai",)


# -- the file is read as what it says it is ----------------------------------


def test_a_key_this_build_does_not_read_is_refused_not_ignored(tmp_path):
    """A misspelled key would collect a round missing whatever it carried."""
    with pytest.raises(SubjectFileError, match="competitor"):
        load_subject(written(tmp_path, altered(competitor=[{"name": "Numerai"}])))


def test_a_file_with_no_subject_at_all_is_refused(tmp_path):
    doc = altered()
    del doc["subject"]

    with pytest.raises(SubjectFileError, match=r"missing \['subject'\]"):
        load_subject(written(tmp_path, doc))


def test_a_prompt_list_that_is_not_a_list_is_refused(tmp_path):
    with pytest.raises(SubjectFileError, match="is a list of questions"):
        load_subject(written(tmp_path, altered(prompts={"m1": "What is marx.finance?"})))


def test_a_file_that_is_not_json_is_refused_with_the_path(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(SubjectFileError, match="is not valid JSON"):
        load_subject(path)


def test_a_file_that_is_not_there_is_refused_with_the_path(tmp_path):
    with pytest.raises(SubjectFileError, match="does not exist"):
        load_subject(tmp_path / "nothing.json")


# -- which questions name the brand they ask about ---------------------------


def test_the_shipped_file_names_the_brand_in_exactly_one_question():
    """m1 asks what marx.finance is, so the name is inside the question.

    That one prompt was worth ten points of the headline on the round this repo
    collected: every answer to it named Marx, and every one of those answers was
    the model saying it had never heard of marx.finance.
    """
    assert load_subject(SHIPPED).self_naming("Marx") == ("m1",)


def test_a_question_carrying_only_an_alias_is_self_naming_too(tmp_path):
    """The declared forms are the whole of what counts, and an alias is one.

    Nothing in this question is the brand's name, so a rule reading the name
    alone would leave it in the rate while the detector kept firing on it.
    """
    doc = altered()
    doc["subject"]["aliases"] = ["Kapital Labs"]
    doc["prompts"] = [
        {"id": "m1", "text": "What does Kapital Labs do?"},
        {"id": "m2", "text": "Agentic finance platforms in 2026"},
    ]
    subject = load_subject(written(tmp_path, doc))

    assert subject.self_naming("Marx") == ("m1",)


def test_a_question_that_does_not_name_the_brand_is_left_in(tmp_path):
    """The rule is per question, so one prompt naming it says nothing about the rest."""
    subject = load_subject(written(tmp_path, VALID))

    assert [p.id for p in subject.prompts] == ["m1", "m2"]
    assert subject.self_naming("Marx") == ("m1",)


def test_the_match_is_the_one_detect_makes_and_not_a_second_rule(tmp_path):
    """Case-insensitive, bounded by non-word characters, literals only."""
    doc = altered()
    doc["subject"]["aliases"] = []
    doc["prompts"] = [
        {"id": "m1", "text": "Who competes with MARX in agentic finance?"},
        {"id": "m2", "text": "Is Marxism a trading strategy?"},
        {"id": "m3", "text": "Alternatives to Numerai for crowdsourced trading signals"},
    ]
    subject = load_subject(written(tmp_path, doc))

    assert subject.self_naming("Marx") == ("m1",)


def test_the_intent_label_is_a_note_and_not_the_rule(tmp_path):
    """Both labels are wrong here and both prompts are still placed correctly.

    `intent` is written by hand, so a rule reading it would be a rule somebody
    can mistype. The question's own text cannot be mistyped without changing
    the question that was asked.
    """
    doc = altered()
    doc["prompts"] = [
        {"id": "m1", "text": "What is marx.finance?", "intent": "category"},
        {"id": "m2", "text": "Agentic finance platforms in 2026", "intent": "entity"},
    ]
    subject = load_subject(written(tmp_path, doc))

    assert subject.self_naming("Marx") == ("m1",)


def test_a_name_the_file_does_not_track_is_refused(tmp_path):
    """Nothing here declares what would count as naming it, so nothing is guessed."""
    subject = load_subject(written(tmp_path, VALID))

    with pytest.raises(ValueError, match="not 'Numerai'"):
        subject.self_naming("Numerai")


def test_a_competitor_is_scored_by_its_own_forms(tmp_path):
    """Each tracked name asks the question about itself, not about the subject."""
    doc = altered(competitors=[{"name": "Numerai", "aliases": ["numer.ai"]}])
    doc["prompts"].append({"id": "m3", "text": "Alternatives to Numerai"})
    subject = load_subject(written(tmp_path, doc))

    assert subject.self_naming("Marx") == ("m1",)
    assert subject.self_naming("Numerai") == ("m3",)


# -- the id has to survive being a file name ---------------------------------


def test_an_id_that_would_split_a_snapshot_name_is_refused(tmp_path):
    """A snapshot is named subject__engine__surface, joined and read back."""
    doc = altered()
    doc["subject"]["id"] = "marx__anthropic"

    with pytest.raises(SubjectFileError, match="fields nobody wrote"):
        load_subject(written(tmp_path, doc))


def test_an_id_that_is_a_path_is_refused(tmp_path):
    doc = altered()
    doc["subject"]["id"] = "../marx"

    with pytest.raises(SubjectFileError, match="a path rather than a name"):
        load_subject(written(tmp_path, doc))


def test_the_diagnostic_name_is_refused_because_nothing_can_score_it(tmp_path):
    """`replay` refuses that subject, so a round there can never be read.

    It would still cost exactly what a real round costs, and the file would
    verify, which is the worst combination available here.
    """
    doc = altered()
    doc["subject"]["id"] = "diagnostic"

    with pytest.raises(SubjectFileError, match="can never be scored"):
        load_subject(written(tmp_path, doc))
