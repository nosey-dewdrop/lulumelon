"""collect: the part that asks, and the part that writes down what it heard.

`mirror` is pure arithmetic over runs. This package produces those runs. The
split is on purpose: the measurement engine must stay reproducible from a file,
so nothing in `mirror` is allowed to reach the network, and nothing here is
allowed to compute a score.
"""

from .ask import (
    SURFACES,
    UNKNOWN_MODEL,
    UNSEARCHED_SURFACE,
    Answer,
    FakeProvider,
    PerplexityProvider,
    Provider,
    Usage,
    is_unsearched_surface,
)
from .budget import (
    CHARS_PER_TOKEN,
    UNMEASURED_INPUT_TOKENS,
    Budget,
    token_ceiling,
    tokens_for_chars,
)
from .detect import Brand, detect, normalise, occurrences
from .ledger import (
    DIAGNOSTIC_SUBJECT,
    GENESIS,
    HASHED_FIELDS,
    ROUND_END,
    SCHEMA_VERSION,
    SEALING_VERSION,
    Ledger,
    LedgerFormatError,
    Record,
    UnknownSchemaVersion,
    decode,
    is_diagnostic,
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
from .subject import Subject, SubjectFileError, load_subject

__all__ = [
    "CHARS_PER_TOKEN",
    "DIAGNOSTIC_SUBJECT",
    "GENESIS",
    "HASHED_FIELDS",
    "INSTRUCTION",
    "INSTRUCTION_VERSION",
    "REPLICA_SURFACE",
    "ROUND_END",
    "SCHEMA_VERSION",
    "SEALING_VERSION",
    "SURFACES",
    "UNKNOWN_MODEL",
    "UNMEASURED_INPUT_TOKENS",
    "UNSEARCHED_SURFACE",
    "Answer",
    "Brand",
    "Budget",
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
    "Subject",
    "SubjectFileError",
    "UnknownSchemaVersion",
    "Usage",
    "decode",
    "detect",
    "is_diagnostic",
    "is_replica_surface",
    "is_unsearched_surface",
    "load_subject",
    "normalise",
    "occurrences",
    "replay",
    "replica_prompt",
    "replica_surface",
    "run_round",
    "scrub",
    "source_fingerprint",
    "storable",
    "token_ceiling",
    "tokens_for_chars",
    "utc_now",
    "without",
]
