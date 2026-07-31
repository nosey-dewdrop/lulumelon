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
before it. Change any earlier line and every later hash stops matching, which
`verify` reports rather than repairs.

Runs that failed are recorded with `status="error"` instead of being dropped.
Dropping them looks tidy and quietly biases the measurement: an engine that
refuses to answer about a brand is telling you something about that brand, and
a collector that silently retries until it gets an answer reports the survivors
only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Sequence

SCHEMA_VERSION = 1

#: First link of a chain. Any value works as long as it is fixed and obvious.
GENESIS = "0" * 64

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")
_PHONE = re.compile(r"(?<![\w.])(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)[ .-]?)?\d{3}[ .-]?\d{2,4}[ .-]?\d{2,4}(?![\w.])")


def scrub(text: str) -> str:
    """Remove the two kinds of personal data a model answer plausibly leaks.

    We ask public, buyer-intent questions, so the expected leak surface is
    small: an answer that quotes a contact page. It is still cheaper to strip
    it on the way in than to explain later why a customer's export contains a
    stranger's phone number. Redaction happens before the hash is computed, so
    the unscrubbed text never exists on disk and never enters the chain.
    """
    text = _EMAIL.sub("[email]", text)
    return _PHONE.sub("[phone]", text)


@dataclass(frozen=True, slots=True)
class Record:
    """One ask, written whole.

    This is a superset of `mirror.Run`. The engine consumes the analysable
    subset; the ledger keeps the rest so a number can be traced back to the
    sentence that produced it.
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
    prev_hash: str = GENESIS
    hash: str = ""
    v: int = SCHEMA_VERSION

    def payload(self) -> dict:
        """The record without its own hash, in a stable key order."""
        d = asdict(self)
        d.pop("hash")
        d["brands"] = list(self.brands)
        d["citations"] = list(self.citations)
        return dict(sorted(d.items()))

    def digest(self) -> str:
        """sha256 over the payload, which includes `prev_hash`."""
        blob = json.dumps(self.payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def sealed(self, prev_hash: str) -> "Record":
        """A copy linked to `prev_hash` and carrying its own digest."""
        linked = Record(**{**self.payload(), "prev_hash": prev_hash, "hash": ""})
        return Record(**{**linked.payload(), "prev_hash": prev_hash, "hash": linked.digest()})


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
        """Reserve the next unused id for this (subject, engine, surface).

        The sequence number is what makes a second run of the same command an
        addition rather than an overwrite. The timestamp is for humans; the
        sequence is what the guarantee rests on, because two rounds inside the
        same second must still be two rounds.
        """
        stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        prefix = f"{subject}__{engine}__{surface}"
        used = {
            int(m.group(1))
            for p in self.root.glob(f"{prefix}__*__*.jsonl")
            if (m := re.search(r"__(\d{4})\.jsonl$", p.name))
        }
        seq = max(used, default=0) + 1
        return f"{prefix}__{stamp}__{seq:04d}"

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
        promised.
        """
        path = self.path_of(snapshot_id)
        tail = self.tail_hash(snapshot_id)
        sealed = Record(
            **{
                **record.payload(),
                "snapshot_id": snapshot_id,
                "seq": self.count(snapshot_id),
                "answer_text": scrub(record.answer_text),
                "prev_hash": tail,
                "hash": "",
            }
        ).sealed(tail)
        line = json.dumps(
            {**sealed.payload(), "hash": sealed.hash},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return sealed

    # -- reading ----------------------------------------------------------

    def read(self, snapshot_id: str) -> Iterator[Record]:
        path = self.path_of(snapshot_id)
        if not path.exists():
            return
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    d["brands"] = tuple(d.get("brands", ()))
                    d["citations"] = tuple(d.get("citations", ()))
                    yield Record(**d)

    def count(self, snapshot_id: str) -> int:
        path = self.path_of(snapshot_id)
        if not path.exists():
            return 0
        with open(path, encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())

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

        Reports rather than repairs. A ledger that silently fixes itself is a
        ledger that cannot be used as evidence.
        """
        problems: list[str] = []
        prev = GENESIS
        for i, rec in enumerate(self.read(snapshot_id)):
            if rec.seq != i:
                problems.append(f"line {i}: seq is {rec.seq}, expected {i}")
            if rec.prev_hash != prev:
                problems.append(f"line {i}: prev_hash does not match the line before it")
            recomputed = rec.digest()
            if recomputed != rec.hash:
                problems.append(f"line {i}: content does not match its own hash")
            prev = recomputed
        return problems
