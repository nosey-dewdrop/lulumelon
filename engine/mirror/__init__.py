"""mirror: a measurement engine for non-deterministic answer engines.

Ask the mirror who the fairest is and it names someone. Ask again and it may
name someone else. Asking once and printing the name is the cheap reading, and
it is one draw. This library asks k times and reports the distribution, the
interval, and whether the movement you are looking at could have been the dice.

Nothing in here calls a model. Given recorded runs it is pure arithmetic and
fully reproducible from a seed, which is the property that makes it an
instrument rather than a dashboard.
"""

from .compare import (
    Verdict,
    design_confounds,
    holm_adjust,
    mcnemar_detection,
    model_confounds,
    paired_difference,
    surface_confounds,
)
from .intervals import Interval, cluster_bootstrap_ci, naive_bootstrap_ci, wilson_interval
from .report import BrandReport, brand_report
from .stability import Stability, jaccard, rbo, stability_of
from .types import PromptSample, Run, Snapshot, group_runs, snapshot_from_runs
from .variance import DesignRequirement, VarianceSplit, decompose, prompts_needed, runs_needed

__all__ = [
    "BrandReport",
    "DesignRequirement",
    "Interval",
    "PromptSample",
    "Run",
    "Snapshot",
    "Stability",
    "VarianceSplit",
    "Verdict",
    "brand_report",
    "cluster_bootstrap_ci",
    "decompose",
    "design_confounds",
    "group_runs",
    "holm_adjust",
    "jaccard",
    "mcnemar_detection",
    "model_confounds",
    "naive_bootstrap_ci",
    "paired_difference",
    "prompts_needed",
    "rbo",
    "runs_needed",
    "snapshot_from_runs",
    "stability_of",
    "surface_confounds",
    "wilson_interval",
]
