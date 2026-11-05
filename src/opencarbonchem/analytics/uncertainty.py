"""Monte Carlo uncertainty propagation.

Each uncertain input is described by a :class:`InputDistribution` around its
base value. The engine computes every row once, then propagates the sampled
multipliers through the *same* linear relation the calculation engine uses
(``E = AD × EF``, and ``CO2e = E × GWP``), so the propagated total is exact for
the model rather than an approximation of it.

Reproducibility is a hard requirement (handover N4): the random generator is
seeded explicitly, inputs are sampled in a deterministic order, and the same
seed therefore yields byte-identical summary statistics.

Reported statistics: mean, median, standard deviation, 5th/95th percentiles,
minimum, maximum, and a variance-share contribution analysis (squared Pearson
correlation of each input with the total, normalised to 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

import numpy as np

from ..core.exceptions import UncertaintyError
from ..core.gwp import DEFAULT_GWP_SET
from .common import InventoryEntry, base_rows, validate_entries
from .sensitivity import PerturbableField

__all__ = [
    "DistributionKind",
    "InputDistribution",
    "Contribution",
    "MonteCarloResult",
    "run_monte_carlo",
    "default_distributions",
]

DistributionKind = Literal["normal", "lognormal", "triangular", "uniform", "fixed"]

_KINDS: tuple[str, ...] = ("normal", "lognormal", "triangular", "uniform", "fixed")
_FIELDS: tuple[str, ...] = ("quantity", "factor_value")


@dataclass(frozen=True)
class InputDistribution:
    """Uncertainty around one input, expressed as a relative spread.

    ``spread_pct`` is the relative half-width / standard deviation in percent:

    * ``normal``      — mean = base, standard deviation = ``spread_pct`` % (truncated at 0)
    * ``lognormal``   — median = base, sigma = ``spread_pct`` % (right-skewed, always > 0)
    * ``triangular``  — (base·(1−s), base, base·(1+s))
    * ``uniform``     — [base·(1−s), base·(1+s)]
    * ``fixed``       — no uncertainty; included so an input can be pinned explicitly
    """

    name: str
    activity_id: str
    field: PerturbableField = "factor_value"
    kind: DistributionKind = "normal"
    spread_pct: float = 10.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise UncertaintyError("Distribution name must not be blank.")
        if not self.activity_id.strip():
            raise UncertaintyError(f"{self.name}: activity_id must not be blank.")
        if self.kind not in _KINDS:
            raise UncertaintyError(
                f"{self.name}: unknown distribution {self.kind!r}; expected one of "
                f"{', '.join(_KINDS)}."
            )
        if self.field not in _FIELDS:
            raise UncertaintyError(
                f"{self.name}: field must be one of {', '.join(_FIELDS)}; got {self.field!r}."
            )
        if self.kind == "fixed":
            if self.spread_pct != 0:
                raise UncertaintyError(
                    f"{self.name}: a fixed input must have spread_pct = 0."
                )
            return
        if not 0 < self.spread_pct < 100:
            raise UncertaintyError(
                f"{self.name}: spread_pct must be in (0, 100) for a {self.kind} "
                f"distribution; got {self.spread_pct!r}."
            )


@dataclass(frozen=True)
class Contribution:
    """Share of total variance attributed to one input."""

    name: str
    activity_id: str
    field: str
    share: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "activity_id": self.activity_id,
            "field": self.field,
            "share": self.share,
        }


@dataclass(frozen=True, eq=False)
class MonteCarloResult:
    """Monte Carlo output: summary statistics plus the raw total samples."""

    base_kg: float
    gwp_set: str
    seed: int
    n_draws: int
    samples: np.ndarray = field(repr=False)
    contributions: tuple[Contribution, ...] = ()

    # -- statistics --------------------------------------------------------- #
    @property
    def mean_kg(self) -> float:
        return float(np.mean(self.samples))

    @property
    def median_kg(self) -> float:
        return float(np.median(self.samples))

    @property
    def std_kg(self) -> float:
        return float(np.std(self.samples, ddof=1)) if self.n_draws > 1 else 0.0

    @property
    def p5_kg(self) -> float:
        return float(np.percentile(self.samples, 5))

    @property
    def p95_kg(self) -> float:
        return float(np.percentile(self.samples, 95))

    @property
    def min_kg(self) -> float:
        return float(np.min(self.samples))

    @property
    def max_kg(self) -> float:
        return float(np.max(self.samples))

    @property
    def relative_std_pct(self) -> float | None:
        mean = self.mean_kg
        return None if mean == 0 else self.std_kg / mean * 100.0

    # -- presentation ------------------------------------------------------- #
    def histogram(self, bins: int = 40) -> dict:
        if bins < 1:
            raise UncertaintyError("histogram bins must be >= 1")
        counts, edges = np.histogram(self.samples, bins=bins)
        return {"counts": counts.tolist(), "edges": edges.tolist()}

    def to_dict(self) -> dict:
        return {
            "base_kg": self.base_kg,
            "gwp_set": self.gwp_set,
            "seed": self.seed,
            "n_draws": self.n_draws,
            "mean_kg": self.mean_kg,
            "median_kg": self.median_kg,
            "std_kg": self.std_kg,
            "relative_std_pct": self.relative_std_pct,
            "p5_kg": self.p5_kg,
            "p95_kg": self.p95_kg,
            "min_kg": self.min_kg,
            "max_kg": self.max_kg,
            "contributions": [c.to_dict() for c in self.contributions],
        }


def _sample(rng: np.random.Generator, dist: InputDistribution, n: int) -> np.ndarray:
    spread = dist.spread_pct / 100.0
    if dist.kind == "fixed":
        return np.ones(n)
    if dist.kind == "normal":
        draws = rng.normal(1.0, spread, n)
        return np.clip(draws, 0.0, None)  # a negative multiplier is physically meaningless
    if dist.kind == "lognormal":
        return np.exp(rng.normal(0.0, spread, n))  # median 1, mean exp(sigma^2 / 2)
    if dist.kind == "triangular":
        return rng.triangular(1.0 - spread, 1.0, 1.0 + spread, n)
    return rng.uniform(1.0 - spread, 1.0 + spread, n)  # uniform


def run_monte_carlo(
    entries: Iterable[InventoryEntry],
    distributions: Iterable[InputDistribution],
    *,
    n_draws: int = 10_000,
    seed: int = 42,
    gwp_set: str = DEFAULT_GWP_SET,
) -> MonteCarloResult:
    """Propagate input uncertainty to the inventory total.

    ``seed`` is recorded on the result so any published interval is reproducible.
    """
    if not isinstance(n_draws, int) or isinstance(n_draws, bool) or n_draws < 1:
        raise UncertaintyError(f"n_draws must be a positive integer; got {n_draws!r}.")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise UncertaintyError(f"seed must be an integer; got {seed!r}.")

    materialised = validate_entries(entries)
    dists = tuple(distributions)
    if not dists:
        raise UncertaintyError("At least one input distribution is required.")

    known = {activity.activity_id for activity, _factor in materialised}
    names: set[str] = set()
    for dist in dists:
        if dist.activity_id not in known:
            raise UncertaintyError(
                f"{dist.name}: activity {dist.activity_id!r} is not in the inventory "
                f"(known IDs: {', '.join(sorted(known))})."
            )
        if dist.name in names:
            raise UncertaintyError(f"Duplicate distribution name {dist.name!r}.")
        names.add(dist.name)

    rows = base_rows(materialised, gwp_set)
    co2e_by_id = {row.activity_id: row.co2e_kg for row in rows}
    base_total = sum(co2e_by_id.values())

    rng = np.random.default_rng(seed)
    samples_by_name: dict[str, np.ndarray] = {}
    # Deterministic sampling order so the same seed always reproduces the run.
    for dist in sorted(dists, key=lambda d: (d.activity_id, d.field, d.name)):
        samples_by_name[dist.name] = _sample(rng, dist, n_draws)

    # Multipliers are multiplicative when one row carries several distributions
    # (e.g. both its quantity and its factor are uncertain).
    multipliers: dict[str, np.ndarray] = {}
    for dist in dists:
        key = dist.activity_id
        multipliers[key] = multipliers.get(key, np.ones(n_draws)) * samples_by_name[dist.name]

    totals = np.full(n_draws, base_total, dtype=float)
    for activity_id, multiplier in multipliers.items():
        contribution = co2e_by_id[activity_id]
        totals += contribution * (multiplier - 1.0)

    # Variance-share attribution via squared Pearson correlation.
    variance = float(np.var(totals))
    contributions: list[Contribution] = []
    if variance > 0:
        strengths = []
        for dist in dists:
            with np.errstate(invalid="ignore"):
                corr = np.corrcoef(samples_by_name[dist.name], totals)[0, 1]
            strength = 0.0 if np.isnan(corr) else float(corr) ** 2
            strengths.append((dist, strength))
        total_strength = sum(strength for _dist, strength in strengths)
        for dist, strength in strengths:
            contributions.append(
                Contribution(
                    name=dist.name,
                    activity_id=dist.activity_id,
                    field=dist.field,
                    share=strength / total_strength if total_strength > 0 else 0.0,
                )
            )
        contributions.sort(key=lambda c: (-c.share, c.name))

    return MonteCarloResult(
        base_kg=base_total,
        gwp_set=gwp_set,
        seed=seed,
        n_draws=n_draws,
        samples=totals,
        contributions=tuple(contributions),
    )


def default_distributions(
    entries: Iterable[InventoryEntry],
    *,
    spread_pct: float = 10.0,
    field_name: PerturbableField = "factor_value",
    use_factor_uncertainty: bool = True,
) -> list[InputDistribution]:
    """Build distributions from each factor's recorded ``uncertainty_pct``.

    Where a factor has no recorded uncertainty, ``spread_pct`` is used and the
    choice is visible in the returned names/values — never silently assumed.
    """
    materialised = validate_entries(entries)
    result: list[InputDistribution] = []
    for activity, factor in materialised:
        spread = (
            factor.uncertainty_pct
            if use_factor_uncertainty and factor.uncertainty_pct is not None
            else spread_pct
        )
        if spread is None or spread <= 0:
            continue
        result.append(
            InputDistribution(
                name=f"{activity.activity_id} · {field_name}",
                activity_id=activity.activity_id,
                field=field_name,
                kind="normal",
                spread_pct=float(min(spread, 99.0)),
            )
        )
    if not result:
        raise UncertaintyError("No factor in the inventory carries a usable uncertainty.")
    return result
