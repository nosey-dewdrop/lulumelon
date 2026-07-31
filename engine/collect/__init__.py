"""collect: the part that asks, and the part that writes down what it heard.

`mirror` is pure arithmetic over runs. This package produces those runs. The
split is on purpose: the measurement engine must stay reproducible from a file,
so nothing in `mirror` is allowed to reach the network, and nothing here is
allowed to compute a score.
"""

from .ask import SURFACES, UNKNOWN_MODEL, Answer, FakeProvider, PerplexityProvider, Provider
from .detect import Brand, detect, normalise, occurrences
from .ledger import GENESIS, SCHEMA_VERSION, Ledger, Record, scrub
from .replay import Replay, replay
from .session import Prompt, RoundResult, run_round, utc_now

__all__ = [
    "GENESIS",
    "SCHEMA_VERSION",
    "SURFACES",
    "UNKNOWN_MODEL",
    "Answer",
    "Brand",
    "FakeProvider",
    "Ledger",
    "PerplexityProvider",
    "Prompt",
    "Provider",
    "Record",
    "Replay",
    "RoundResult",
    "detect",
    "normalise",
    "occurrences",
    "replay",
    "run_round",
    "scrub",
    "utc_now",
]
