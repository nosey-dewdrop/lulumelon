"""collect: the part that asks, and the part that writes down what it heard.

`mirror` is pure arithmetic over runs. This package produces those runs. The
split is on purpose: the measurement engine must stay reproducible from a file,
so nothing in `mirror` is allowed to reach the network, and nothing here is
allowed to compute a score.
"""

from .ask import SURFACES, UNKNOWN_MODEL, Answer, FakeProvider, PerplexityProvider, Provider, Usage
from .detect import Brand, detect, normalise, occurrences
from .ledger import (
    GENESIS,
    HASHED_FIELDS,
    SCHEMA_VERSION,
    Ledger,
    LedgerFormatError,
    Record,
    UnknownSchemaVersion,
    decode,
    scrub,
    storable,
)
from .replay import Replay, replay
from .replica import (
    INSTRUCTION,
    INSTRUCTION_VERSION,
    REPLICA_SURFACE,
    ReplicaProvider,
    is_replica_surface,
    replica_prompt,
    replica_surface,
    source_fingerprint,
    without,
)
from .session import Prompt, RoundResult, run_round, utc_now

__all__ = [
    "GENESIS",
    "INSTRUCTION",
    "INSTRUCTION_VERSION",
    "REPLICA_SURFACE",
    "HASHED_FIELDS",
    "SCHEMA_VERSION",
    "SURFACES",
    "UNKNOWN_MODEL",
    "Answer",
    "Brand",
    "FakeProvider",
    "Ledger",
    "LedgerFormatError",
    "PerplexityProvider",
    "Prompt",
    "Provider",
    "Record",
    "Replay",
    "ReplicaProvider",
    "RoundResult",
    "UnknownSchemaVersion",
    "Usage",
    "decode",
    "detect",
    "is_replica_surface",
    "normalise",
    "occurrences",
    "replay",
    "replica_prompt",
    "replica_surface",
    "run_round",
    "scrub",
    "source_fingerprint",
    "storable",
    "utc_now",
    "without",
]
