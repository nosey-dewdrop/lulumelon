"""What a round is about: the names it tracks and the questions it asks.

A subject file is the only input to a measurement that a person writes by hand,
and it decides two things that nothing downstream can recover. Which strings
count as a mention of the brand is one, and it is a declaration rather than a
guess, because `detect` matches literals and nothing else. What each question is
called is the other, and a prompt id is permanent identity: `mirror` groups by
it, so two rounds are comparable only where the same id means the same question
in both.

That is why this file refuses rather than repairs.

**A prompt id is never invented and never renumbered.** A loader that filled in
missing ids, or quietly made a duplicate unique, would produce a round that
loads cleanly and pairs the wrong questions against each other the first time
anybody compares two of them. The wrong pairing is invisible: both sides have
the same number of prompts and the arithmetic runs. So a file with two prompts
under one id is refused by name, and so is a prompt with no id at all.

**A round that cannot mean anything is refused before it can cost anything.**
No prompts, a brand with no name, an empty question: each of those produces a
file on disk that looks like a measurement and holds none, after the money has
been spent. They are cheap to detect here and impossible to detect later.

**Keys this build does not read are refused, not ignored.** A file whose
`competitors` is spelled `competitor` would otherwise collect a round tracking
one name while its author believed it tracked five, and nothing on screen would
disagree. This is the same rule the ledger applies to a line it reads: a
document is accepted as what it says it is, or not at all.

**The subject id has to survive being a file name.** It is what the snapshot is
called on disk, and the ledger builds that name by joining fields with a double
underscore, so an id carrying one of those would split a name into fields that
were never there. `diagnostic` is refused for the same reason from the other
direction: it is the name a check call is filed under, and `replay` refuses to
score anything filed under it, so a measurement collected there would be a round
that cost money and can never be read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .detect import Brand
from .ledger import DIAGNOSTIC_SUBJECT
from .session import Prompt

#: Top-level keys a subject file may carry. `projects` and `competitors` are
#: both lists of tracked names beside the subject itself: a name listed in
#: either is a name the round reports on, and a name listed and not tracked
#: would be one its author believes is being measured and is not.
FILE_KEYS = frozenset({"subject", "projects", "competitors", "prompts"})

#: Keys of one tracked name. The subject and a competitor are written the same
#: way because they become the same thing, a `Brand` with its declared forms.
BRAND_KEYS = frozenset({"id", "name", "domain", "aliases", "ambiguousName"})

#: Keys of one question. `intent` and `axis` are read by nobody here and are
#: still named: they describe why a question is in the set, which is a note to
#: whoever maintains the file, and refusing them would refuse the file.
PROMPT_KEYS = frozenset({"id", "text", "intent", "axis"})

#: What the ledger joins a snapshot's fields with. An id carrying one would
#: read back as more fields than were written.
_FIELD_SEPARATOR = "__"


class SubjectFileError(ValueError):
    """A subject file will not produce a round worth paying for.

    A `ValueError`, so the CLI reports it the way it reports every other
    refusal, with the path and the reason and no traceback.
    """


@dataclass(frozen=True, slots=True)
class Subject:
    """One subject file, read.

    `id` is what the round is filed under, `brands` is every name the round
    reports on with the subject first, and `prompts` carry the ids they will
    keep for the rest of their lives.

    `ambiguous_name` is the file's own warning about itself: the subject's name
    is a word that means something else as well. It changes no arithmetic here,
    because what counts as a mention is the declared list of forms and nothing
    else, and it is carried so the person spending the money is told before
    they spend it.
    """

    id: str
    name: str
    brands: tuple[Brand, ...]
    prompts: tuple[Prompt, ...]
    ambiguous_name: bool
    path: Path

    @property
    def competitors(self) -> tuple[Brand, ...]:
        """Every tracked name except the subject, in the order they were listed."""
        return self.brands[1:]


def load_subject(path: Path) -> Subject:
    """Read one subject file, or say exactly what is wrong with it.

    Every refusal below names the file and the field, because this is the one
    input a person edits by hand and a message that says only "invalid" sends
    them back to a document they have already read.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SubjectFileError(
            f"{path} does not exist, so there is no subject to collect a round about"
        ) from None
    except OSError as e:
        raise SubjectFileError(f"{path} could not be read: {e.strerror}") from None
    except json.JSONDecodeError as e:
        raise SubjectFileError(f"{path} is not valid JSON: {e}") from None

    if not isinstance(raw, dict):
        raise SubjectFileError(
            f"{path} holds a {type(raw).__name__} and a subject file is an object"
        )
    _check_keys(path, "the file", raw, FILE_KEYS, required=("subject", "prompts"))

    tracked: list[tuple[str, Brand]] = [("subject", _brand_entry(path, "subject", raw["subject"]))]
    for key in ("projects", "competitors"):
        listed = raw.get(key, [])
        if not isinstance(listed, list):
            raise SubjectFileError(
                f"{path}: {key} holds a {type(listed).__name__} and is a list of tracked names"
            )
        for i, entry in enumerate(listed):
            where = f"{key}[{i}]"
            tracked.append((where, _brand_entry(path, where, entry)))

    seen: dict[str, str] = {}
    for where, brand in tracked:
        folded = brand.name.casefold()
        if folded in seen:
            raise SubjectFileError(
                f"{path}: {where} is named {brand.name!r}, which {seen[folded]} already is. "
                "detection reports one line per name, so the second would never appear on its "
                "own and one of the two would be silently unmeasured"
            )
        seen[folded] = where

    return Subject(
        id=_subject_id(path, raw["subject"]),
        name=tracked[0][1].name,
        brands=tuple(brand for _, brand in tracked),
        prompts=_prompts(path, raw["prompts"]),
        ambiguous_name=bool(raw["subject"].get("ambiguousName", False)),
        path=path,
    )


def _check_keys(
    path: Path, where: str, node: dict, allowed: frozenset[str], *, required: tuple[str, ...] = ()
) -> None:
    """Refuse a key this build does not read, and a key it needs and lacks.

    Both directions, for the same reason the ledger refuses both: an unknown
    key is usually a known key spelled wrong, and reading around it produces a
    round missing whatever that key was carrying.
    """
    unknown = sorted(set(node) - allowed)
    if unknown:
        raise SubjectFileError(
            f"{path}: {where} carries {unknown}, which this build does not read. a key it does "
            f"not read is usually one of {sorted(allowed)} spelled wrong, and reading past it "
            "would collect a round missing whatever it was carrying"
        )
    missing = [name for name in required if name not in node]
    if missing:
        raise SubjectFileError(f"{path}: {where} is missing {missing}")


def _text(path: Path, where: str, node: dict, key: str) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SubjectFileError(
            f"{path}: {where}.{key} is {value!r}, and it has to be a string with something in it"
        )
    return value.strip()


def _brand_entry(path: Path, where: str, node: object) -> Brand:
    """One tracked name and the literal forms that count as naming it.

    The aliases are taken exactly as written and nothing is added to them, not
    even the domain sitting in the field next door. What counts as a mention is
    the author's declaration, and a loader that quietly widened it would change
    the number without changing the file it is supposed to be reproducible from.
    """
    if not isinstance(node, dict):
        raise SubjectFileError(
            f"{path}: {where} holds a {type(node).__name__} and a tracked name is an object "
            "with a name and its aliases"
        )
    _check_keys(path, where, node, BRAND_KEYS, required=("name",))
    aliases = node.get("aliases", [])
    if not isinstance(aliases, list):
        raise SubjectFileError(
            f"{path}: {where}.aliases holds a {type(aliases).__name__} and is a list of the "
            "other strings that count as this name"
        )
    for i, alias in enumerate(aliases):
        if not isinstance(alias, str) or not alias.strip():
            raise SubjectFileError(
                f"{path}: {where}.aliases[{i}] is {alias!r}; an empty alias counts as nothing "
                "and would sit in the file looking like a declared form"
            )
    return Brand(
        name=_text(path, where, node, "name"),
        aliases=tuple(alias.strip() for alias in aliases),
    )


def _subject_id(path: Path, node: dict) -> str:
    """The name every snapshot of this subject is filed under.

    Checked against the ledger's own naming rather than against a general idea
    of a safe string: it is joined into a file name with the engine and the
    surface, and it must not be able to look like more fields than it is.
    """
    subject_id = _text(path, "subject", node, "id")
    if _FIELD_SEPARATOR in subject_id or any(c.isspace() for c in subject_id):
        raise SubjectFileError(
            f"{path}: subject.id is {subject_id!r}, and a snapshot is named by joining the "
            f"subject, the engine and the surface with {_FIELD_SEPARATOR!r}, so an id carrying "
            "one of those or a space reads back as fields nobody wrote"
        )
    if subject_id != Path(subject_id).name or subject_id in (".", ".."):
        raise SubjectFileError(
            f"{path}: subject.id is {subject_id!r}, which is a path rather than a name, and it "
            "is used as the first part of a file name"
        )
    if subject_id == DIAGNOSTIC_SUBJECT:
        raise SubjectFileError(
            f"{path}: subject.id is {DIAGNOSTIC_SUBJECT!r}, which is the name a check call is "
            "filed under. a round collected there is refused by replay and can never be "
            "scored, so it would cost money and produce nothing readable"
        )
    return subject_id


def _prompts(path: Path, listed: object) -> tuple[Prompt, ...]:
    """Every question, with the id it keeps for the rest of its life.

    Duplicate ids are refused rather than made unique. Renumbering here would
    be a silent edit to the identity `mirror` groups by, and the round it
    produced would pair two different questions in every comparison anybody
    ever ran against it.
    """
    if not isinstance(listed, list):
        raise SubjectFileError(
            f"{path}: prompts holds a {type(listed).__name__} and is a list of questions"
        )
    if not listed:
        raise SubjectFileError(
            f"{path}: prompts is empty, and a round with no questions asks nothing and measures "
            "nothing"
        )
    prompts: list[Prompt] = []
    seen: dict[str, int] = {}
    for i, entry in enumerate(listed):
        where = f"prompts[{i}]"
        if not isinstance(entry, dict):
            raise SubjectFileError(
                f"{path}: {where} holds a {type(entry).__name__} and a question is an object "
                "with an id and its text"
            )
        _check_keys(path, where, entry, PROMPT_KEYS, required=("id", "text"))
        prompt_id = _text(path, where, entry, "id")
        if prompt_id in seen:
            raise SubjectFileError(
                f"{path}: {where} and prompts[{seen[prompt_id]}] are both called {prompt_id!r}. "
                "a prompt id is permanent identity and is what every comparison groups by, so "
                "two questions under one id are pooled into one sample and paired against the "
                "wrong question in every round that follows"
            )
        seen[prompt_id] = i
        prompts.append(Prompt(id=prompt_id, text=_text(path, where, entry, "text")))
    return tuple(prompts)
