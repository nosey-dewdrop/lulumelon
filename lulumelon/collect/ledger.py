"""The ledger: the only thing in this repo that writes.

Everything under `mirror/` is arithmetic over runs that already exist. This
module is where a run becomes a fact on disk, and it is deliberately the most
paranoid file in the project, for two reasons.

The first is the product. We sell the claim that a competitor's number is not
defensible. That claim is worth nothing if our own number cannot survive
someone asking "show me the raw answers behind this interval". So every ask is
written whole, including the ones that failed, and nothing is ever edited in
place.

The second is that the history is the asset. A day that was not measured cannot
be measured later at any price, and a day that was measured but silently
rewritten is worse than one that was missed, because it looks like evidence.
So the file format is append-only and each record carries the hash of the one
before it.

**What the chain does and does not promise.** Every line present is checked
against its own content and against the line before it, so altering a record in
the middle of a file costs a rewrite of every record after it. That is the
property that makes an old measurement expensive to fake. It is not a
completeness guarantee: removing lines from the *end* of a file leaves nothing
behind to notice, because no record states how long the round was meant to be.
That hole is named in `tests/test_ledger.py` as a failing test rather than a
comment, and it closes when a round learns to seal its own length.

Runs that failed are recorded with `status="error"` instead of being dropped.
Dropping them looks tidy and quietly biases the measurement: an engine that
refuses to answer about a brand is telling you something about that brand, and
a collector that silently retries until it gets an answer reports the survivors
only.

**Schema changes.** Adding a column to a hashed record is the one edit that can
make an honest archive look forged. If a new field joined the hash, every line
written before it would recompute to a different digest and `verify` would
report the customer's own history as tampered with. So a record hashes exactly
the fields *its own version* declared, and each version's field set is written
out below as a literal. Old rows are never edited; a new field opens a new row.
Fields are add-only forever: renaming or removing one makes an old row name a
field that no longer exists, and every historical snapshot becomes unreadable.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from .ask import Usage

SCHEMA_VERSION = 2

#: First link of a chain. Any value works as long as it is fixed and obvious.
GENESIS = "0" * 64

# -- what each version hashed ------------------------------------------------
#
# Both rows are spelled out in full. Writing `_V2 = _V1 | {...}` would be
# shorter and would mean that deleting one name from the v1 line silently
# rewrites two promises at once. A row is a statement about bytes that are
# already on disk, so it is a literal a diff can show.

_V1 = frozenset(
    {
        "snapshot_id", "seq", "prompt_id", "repeat", "engine", "surface",
        "model", "asked_at", "status", "latency_ms", "answer_text",
        "brands", "citations", "provider", "error", "prev_hash", "v",
    }
)

_V2 = frozenset(
    {
        "snapshot_id", "seq", "prompt_id", "repeat", "engine", "surface",
        "model", "asked_at", "status", "latency_ms", "answer_text",
        "brands", "citations", "provider", "error",
        "input_tokens", "output_tokens", "search_context", "reported_cost_usd",
        "prev_hash", "v",
    }
)

#: Version -> the field names that version put inside its sha256. Frozen rows
#: are pinned against a golden file in `tests/test_ledger_golden.py`, so an edit
#: here fails the suite instead of turning a customer's archive red.
HASHED_FIELDS: dict[int, frozenset[str]] = {1: _V1, 2: _V2}


class LedgerFormatError(ValueError):
    """A line on disk is not something this build can read as a record.

    Raised by `read`, which cannot hand a partial view of an evidence file to
    an engine that would then compute an interval from it. `verify` catches
    this and reports it instead, because a diagnostic that raises stops at the
    first problem and the point of a diagnostic is to find all of them.
    """


class UnknownSchemaVersion(LedgerFormatError):
    """The line was written by a newer build than this one.

    Separate from a corrupt line because the remedy is different and the file
    is probably fine: upgrade, do not investigate.
    """


_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")

#: Digits a run has to carry before it is a phone number rather than a figure.
#: Seven is the shortest subscriber number still in service; E.164 caps the
#: whole thing, country code included, at fifteen.
_PHONE_DIGITS = range(7, 16)

#: Characters allowed between the digits of one number. A full stop is
#: deliberately not among them: it is how a decimal is written, and a rule that
#: took it would redact `0.005182` out of an answer about money.
_PHONE_GROUPING = "\u00a0 ()-"

#: A run of digits and grouping characters, bounded so it cannot begin inside a
#: word, a decimal or a URL path. Whether it is a phone number is then decided
#: by `_is_phone`, from the digits it carries: what separates a number somebody
#: can be reached on from a figure is how many digits it has, and that is a
#: count rather than a shape. The previous pattern here was a shape, and it left
#: `+90 532 111 22 33` on disk as `[phone] 33`.
_PHONE_CANDIDATE = re.compile(r"(?<![\w./=])\(?\+?\d[\d\u00a0 ()-]{4,24}\d(?!\w)")


def _is_phone(candidate: str) -> bool:
    """Whether one candidate run is a number somebody could be reached on.

    Three ways to qualify and a bare eight-digit run is none of them: an
    international prefix, digits written in groups, or enough digits that
    nothing else is plausibly that long. The last clause catches `05321112233`
    typed without spaces, and it begins at ten rather than seven because an
    ungrouped seven-digit run is more often an identifier.
    """
    digits = sum(ch.isdigit() for ch in candidate)
    if digits not in _PHONE_DIGITS:
        return False
    return (
        candidate.lstrip("(").startswith("+")
        or any(ch in _PHONE_GROUPING for ch in candidate)
        or digits >= 10
    )


#: Surrogates in this range are how `surrogateescape` carries a byte that is
#: not valid UTF-8. They are produced by *reading* a damaged file, never by
#: writing one, and they must survive a round trip or corruption stops being
#: detectable.
_ESCAPED_BYTE_RANGE = range(0xDC80, 0xDD00)

_LONE_SURROGATE = "�"


def storable(text: str) -> str:
    """Replace characters that cannot be encoded, and leave everything else.

    A provider's JSON can contain an escaped unpaired surrogate — half of an
    emoji whose other half was dropped somewhere upstream. It survives
    `json.loads` and then cannot be encoded to UTF-8 at all, so writing it
    aborts the round at that ask and leaves a short file that reads exactly
    like a complete one. That is the truncation hole arriving through the front
    door, so the character is replaced here, before the hash, and the
    replacement is part of the record rather than a repair applied later.

    Bytes carried in by `surrogateescape` are deliberately left alone: those
    appear only when reading a file that was damaged after it was written, and
    they have to encode back to the same bytes for the damage to be reported.
    """
    if not any(0xD800 <= ord(ch) <= 0xDFFF for ch in text):
        return text
    return "".join(
        ch if ord(ch) in _ESCAPED_BYTE_RANGE or not 0xD800 <= ord(ch) <= 0xDFFF else _LONE_SURROGATE
        for ch in text
    )


def scrub(text: str) -> str:
    """Remove the two kinds of personal data a stored string plausibly leaks.

    We ask public, buyer-intent questions, so the expected leak surface is
    small: an answer that quotes a contact page, or a provider error whose body
    quotes one back at us. It is still cheaper to strip it on the way in than
    to explain later why a customer's export contains a stranger's phone
    number. Redaction happens before the hash is computed, so the unscrubbed
    text never exists on disk and never enters the chain, which also means it
    cannot be removed afterwards without reforging the tail.

    A redaction that leaves part of the thing behind has not redacted it, so
    the phone rule replaces a whole run or none of it.
    """
    text = _EMAIL.sub("[email]", text)
    return _PHONE_CANDIDATE.sub(
        lambda m: "[phone]" if _is_phone(m.group(0)) else m.group(0), text
    )


@dataclass(frozen=True, slots=True)
class Record:
    """One ask, written whole.

    This is a superset of `mirror.Run`. The engine consumes the analysable
    subset; the ledger keeps the rest so a number can be traced back to the
    sentence that produced it, and so a dollar figure can be traced back to the
    call that was billed.

    The four usage fields default to `None`, never to `0`. A zero token count
    is a claim that the provider metered the call and it cost nothing; `None`
    is the absence of a claim. Keeping them apart is the difference between "we
    did not observe this" and "we observed nothing", and only one of those is
    honest when a provider renames a field.
    """

    snapshot_id: str
    seq: int
    prompt_id: str
    repeat: int
    engine: str
    surface: str
    model: str
    asked_at: str
    status: str
    latency_ms: int
    answer_text: str
    brands: tuple[str, ...]
    citations: tuple[str, ...]
    provider: str
    error: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    search_context: str | None = None
    reported_cost_usd: float | None = None
    prev_hash: str = GENESIS
    hash: str = ""
    v: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        # `type(...) is not int` rather than isinstance: bool is a subclass of
        # int, so a JSON `true` would otherwise be a silent alias for schema 1.
        if type(self.v) is not int or self.v not in HASHED_FIELDS:
            raise ValueError(
                f"schema v{self.v!r} is not one this build knows ({sorted(HASHED_FIELDS)})"
            )
        keep = HASHED_FIELDS[self.v]
        carried = sorted(
            name for name in _AFTER_V1 if name not in keep and getattr(self, name) is not None
        )
        if carried:
            raise ValueError(
                f"a v{self.v} record cannot carry {', '.join(carried)}: a v{self.v} payload "
                "has no such key, so the value would be dropped on the way to disk and any "
                "cost computed from it would have no record behind it"
            )
        if self.reported_cost_usd is not None and not math.isfinite(self.reported_cost_usd):
            raise ValueError(
                "reported_cost_usd must be finite; a non-finite cost is neither JSON nor money"
            )

    def payload(self) -> dict:
        """The record without its own hash, carrying only its version's fields.

        Lossy on purpose. A v1 record read by this build has the v2 attributes
        set to None, and they must not reach the digest, or the honest file it
        came from would stop verifying. This is why nothing reconstructs a
        Record from `payload()` any more; `dataclasses.replace` does that job.
        """
        keep = HASHED_FIELDS[self.v]
        d = {name: getattr(self, name) for name in sorted(keep)}
        if "brands" in keep:
            d["brands"] = list(self.brands)
        if "citations" in keep:
            d["citations"] = list(self.citations)
        return d

    def digest(self) -> str:
        """sha256 over the payload, which includes `prev_hash` and `v`.

        Encoded with `surrogateescape` so this is total. A byte flipped inside
        an answer survives reading as a lone surrogate and must come back out
        as the same byte, which makes the digest disagree with the stored hash
        and turns the corruption into a finding. Raising here instead would
        take down `verify`, which is documented as returning a report.
        """
        return hashlib.sha256(self.as_blob().encode("utf-8", errors="surrogateescape")).hexdigest()

    def as_blob(self) -> str:
        """Canonical encoding of the payload. `allow_nan` off: NaN and Infinity
        are not JSON, and a writer that can emit them produces a file our own
        verifier calls intact and every other parser rejects."""
        return json.dumps(
            self.payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False
        )

    def as_line(self) -> str:
        """The exact bytes this record belongs on disk as."""
        return json.dumps(
            {**self.payload(), "hash": self.hash},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )

    def sealed(self, prev_hash: str) -> "Record":
        """A copy linked to `prev_hash` and carrying its own digest."""
        linked = replace(self, prev_hash=prev_hash, hash="")
        return replace(linked, hash=linked.digest())

    def usage(self) -> Usage | None:
        """What the provider said this call consumed, or None when this
        record's schema had nowhere to put it.

        Two different states that must never merge. `usage() is None` means the
        version predates the fields, so nothing was or could have been
        recorded. A returned `Usage` whose `.known` is False means the version
        had the fields and the provider said nothing. Only the second is
        evidence about the provider.
        """
        if "input_tokens" not in HASHED_FIELDS[self.v]:
            return None
        return Usage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            search_context=self.search_context,
            cost_usd=self.reported_cost_usd,
        )


#: Fields that exist on `Record` today but were not in the first schema. Used
#: to refuse a record that carries a value its own version cannot store.
_AFTER_V1 = tuple(sorted({f.name for f in fields(Record)} - _V1 - {"hash"}))


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
    """Refuse a JSON object with the same key twice.

    Python keeps the last such key and several other readers keep the first, so
    a duplicated key is a line that says one thing to our verifier and another
    to whoever audits it. Cheap to plant, invisible to a digest computed over a
    reparse.
    """
    seen: dict = {}
    for key, value in pairs:
        if key in seen:
            raise LedgerFormatError(f"the key {key!r} appears twice on one line")
        seen[key] = value
    return seen


def decode(raw: object) -> Record:
    """A written line, read as the version it says it is.

    Refuses rather than guesses, in both directions. A key outside the line's
    own version was never covered by that line's hash, so accepting it would
    let anything be appended to an old record for free. A key the version
    required and the line lacks is a claim the file has stopped making, and
    filling it in from a default would forge that claim.
    """
    if not isinstance(raw, dict):
        raise LedgerFormatError(f"a ledger line must be a JSON object, got {type(raw).__name__}")
    v = raw.get("v")
    if type(v) is not int:
        raise LedgerFormatError(f"the line does not declare an integer schema version (v={v!r})")
    keep = HASHED_FIELDS.get(v)
    if keep is None:
        raise UnknownSchemaVersion(
            f"schema v{v} was written by a newer build; this one knows {sorted(HASHED_FIELDS)}"
        )
    unknown = sorted(set(raw) - keep - {"hash"})
    if unknown:
        raise LedgerFormatError(f"carries {unknown}, which schema v{v} never hashed")
    missing = sorted(keep - set(raw))
    if missing:
        raise LedgerFormatError(f"is missing {missing}, which schema v{v} hashed")

    d = {name: raw[name] for name in keep}
    d["hash"] = raw.get("hash", "")
    d["brands"] = tuple(d.get("brands") or ())
    d["citations"] = tuple(d.get("citations") or ())
    return Record(**d)


class Ledger:
    """An append-only directory of snapshots.

    One snapshot is one measurement round. Asking again does not touch the
    previous round; it opens the next numbered one beside it. There is no code
    path here that opens a file for writing, only for appending, and no code
    path that deletes.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- naming -----------------------------------------------------------

    def next_snapshot_id(self, subject: str, engine: str, surface: str, *, now: datetime | None = None) -> str:
        """Take the next unused id for this (subject, engine, surface), and keep it.

        The sequence number is what makes a second run of the same command an
        addition rather than an overwrite. The timestamp is for humans; the
        sequence is what the guarantee rests on, because two rounds inside the
        same second must still be two rounds.

        **The name is claimed by creating the file, not by returning a string.**
        Scanning the directory and handing back the next free number reserves
        nothing: two collectors started against one directory in the same second
        both scan, both see the same highest number, and both are told they own
        it. What follows is two rounds appended into one file, interleaved,
        under one snapshot id, and the chain over them verifies clean because
        every link really was written in the order it landed. That is the one
        corruption this format cannot report, so it is prevented instead: the
        file is created `O_EXCL`, the loser of the race gets `FileExistsError`
        and moves to the next number, and the empty file left behind is the
        reservation.

        The directory entry is fsynced, because a reservation that a crash can
        forget is not one.
        """
        stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        prefix = f"{subject}__{engine}__{surface}"
        used = {
            int(m.group(1))
            for p in self.root.glob(f"{prefix}__*__*.jsonl")
            if (m := re.search(r"__(\d{4})\.jsonl$", p.name))
        }
        seq = max(used, default=0) + 1
        while True:
            candidate = f"{prefix}__{stamp}__{seq:04d}"
            try:
                fd = os.open(
                    self.path_of(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644
                )
            except FileExistsError:
                seq += 1
                continue
            os.close(fd)
            self._fsync_dir()
            return candidate

    def _fsync_dir(self) -> None:
        """Make a directory entry durable, so a name survives losing power."""
        dir_fd = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def path_of(self, snapshot_id: str) -> Path:
        return self.root / f"{snapshot_id}.jsonl"

    def snapshots(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.jsonl"))

    # -- writing ----------------------------------------------------------

    def append(self, snapshot_id: str, record: Record) -> Record:
        """Seal `record` onto the end of `snapshot_id` and flush it to disk.

        Opened in append mode and fsynced per record. That is slower than
        buffering and it is the right trade: a crash halfway through a round
        should cost the runs it did not reach, never the ones it already
        promised. When the file is new the directory is fsynced too, so a crash
        loses the tail of a round rather than the whole round.

        Old schema versions are read forever and written never. A build that
        could still write v1 would be a build that could quietly downgrade a
        round, and the four fields this version added are the ones a cost claim
        rests on.
        """
        if record.v != SCHEMA_VERSION:
            raise ValueError(
                f"this build writes schema v{SCHEMA_VERSION} and was handed a v{record.v} "
                "record; older versions are readable but never written"
            )
        path = self.path_of(snapshot_id)
        is_new = not path.exists()
        tail = self.tail_hash(snapshot_id)
        sealed = replace(
            record,
            snapshot_id=snapshot_id,
            seq=self.count(snapshot_id),
            answer_text=scrub(storable(record.answer_text)),
            # The provider's error body reaches here with up to a few hundred
            # characters of its own words, which have quoted a contact address
            # before now. Once hashed it cannot be taken out again.
            error=scrub(storable(record.error)),
            prev_hash=tail,
            hash="",
        ).sealed(tail)
        # `surrogateescape` on the way out as well as in. A model answer has
        # arrived carrying an unpaired surrogate before now; refusing it here
        # would abort the round at that ask and leave a stump on disk that
        # looks exactly like a completed one.
        with open(path, "a", encoding="utf-8", errors="surrogateescape") as fh:
            fh.write(sealed.as_line() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        if is_new:
            self._fsync_dir()
        return sealed

    # -- reading ----------------------------------------------------------

    def _raw_lines(self, snapshot_id: str) -> Iterator[str]:
        """Every non-blank line, decoded so a flipped byte is data, not a crash.

        `surrogateescape` keeps an undecodable byte addressable instead of
        raising out of a function documented as returning a report. It will not
        re-encode to the same canonical form, so the corruption still surfaces
        as a digest mismatch, which is where it belongs.
        """
        path = self.path_of(snapshot_id)
        if not path.exists():
            return
        with open(path, "rb") as fh:
            for raw in fh:
                line = raw.decode("utf-8", errors="surrogateescape").strip()
                if line:
                    yield line

    def read(self, snapshot_id: str) -> Iterator[Record]:
        """Every record in a snapshot, or an exception naming the first bad line.

        Raises where `verify` reports. An engine downstream computes intervals
        from whatever this yields, and handing it the readable half of a
        damaged file would produce a number with a piece of the evidence
        missing and nothing on screen to say so.
        """
        path = self.path_of(snapshot_id)
        for i, line in enumerate(self._raw_lines(snapshot_id)):
            try:
                yield decode(json.loads(line, object_pairs_hook=_reject_duplicates))
            except LedgerFormatError as e:
                raise LedgerFormatError(f"{path}, line {i}: {e}") from e
            except json.JSONDecodeError as e:
                raise LedgerFormatError(f"{path}, line {i}: not valid JSON ({e})") from e

    def count(self, snapshot_id: str) -> int:
        return sum(1 for _ in self._raw_lines(snapshot_id))

    def tail_hash(self, snapshot_id: str) -> str:
        last = GENESIS
        for rec in self.read(snapshot_id):
            last = rec.hash
        return last

    # -- checking ---------------------------------------------------------

    def verify(self, snapshot_id: str) -> list[str]:
        """Recompute the chain from content. Empty list means the file is intact.

        The chain is walked using each record's *recomputed* digest, never the
        hash it carries, so an edited answer is reported twice: once as a line
        whose content no longer matches its own hash, and once as the next line
        whose back-pointer no longer resolves.

        The guarantee is narrower than "everything after it breaks" and
        stronger than it sounds. A single edit breaks exactly one link, but the
        only way to make that link resolve again is to restate the following
        record, which moves the break one line down. Repairing a doctored
        history therefore costs a rewrite of every record after the change,
        which is the property that makes an old measurement expensive to fake.

        Reports rather than repairs, and never raises. An unreadable line is a
        finding, not the end of the walk: stopping there would let one planted
        byte decide where the audit ends and hide every forgery after it.
        """
        problems: list[str] = []
        path = self.path_of(snapshot_id)
        if not path.exists():
            return [
                f"{path} does not exist, so there is nothing to check; a snapshot that was "
                "measured and is now missing cannot be told from one that was never written"
            ]

        prev: str | None = GENESIS
        seen = 0
        for i, line in enumerate(self._raw_lines(snapshot_id)):
            seen += 1
            try:
                rec = decode(json.loads(line, object_pairs_hook=_reject_duplicates))
            except Exception as e:  # noqa: BLE001 - a diagnostic must not raise
                problems.append(
                    f"line {i}: unreadable ({type(e).__name__}: {e}); the link into line {i + 1} "
                    "cannot be checked"
                )
                prev = None
                continue

            try:
                if line != rec.as_line():
                    problems.append(
                        f"line {i}: the bytes on disk are not the canonical encoding of what they "
                        "decode to, so the hash covers a reparse rather than the file"
                    )
                if rec.snapshot_id != snapshot_id:
                    problems.append(
                        f"line {i}: says it belongs to snapshot {rec.snapshot_id!r}, "
                        f"but it is filed as {snapshot_id!r}"
                    )
                if rec.seq != i:
                    problems.append(f"line {i}: seq is {rec.seq}, expected {i}")
                if prev is None:
                    problems.append(
                        f"line {i}: prev_hash cannot be checked, the line before it is unreadable"
                    )
                elif rec.prev_hash != prev:
                    problems.append(f"line {i}: prev_hash does not match the line before it")
                recomputed = rec.digest()
                if recomputed != rec.hash:
                    problems.append(f"line {i}: content does not match its own hash")
                prev = recomputed
            except Exception as e:  # noqa: BLE001 - a report must not become a traceback
                problems.append(f"line {i}: could not be checked ({type(e).__name__}: {e})")
                prev = None

        if seen == 0:
            problems.append(
                f"{path} has no records: the name was claimed and nothing was ever written "
                "under it, so this is a round that did not happen rather than one that did"
            )
        return problems
