"""Emission factor registry: storage, provenance loading and resolution.

Resolution is deterministic and fail-safe. Given an activity's category and
substance the registry:

1. filters candidates by category and substance (case/separator-insensitive);
2. applies the gas constraint — an explicit gas matches that gas or a combined
   ``CO2e`` factor; without an explicit gas, a substance carrying factors for
   several different gases is *ambiguous* and raises
   :class:`AmbiguousFactorError` (the engine will not silently pick one gas);
3. ranks geography — an exact geography match beats ``GLOBAL``; anything else
   is not applicable and is dropped;
4. ranks vintage — the newest factor at or before the reporting year wins;
   a factor from the future relative to the reporting year is rejected with
   :class:`MissingFactorError`;
5. if two survivors are indistinguishable, raises :class:`AmbiguousFactorError`
   rather than choosing arbitrarily.

Failures raise typed errors from the ``OpenCarbonChemError`` hierarchy; the
registry never returns ``None``.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Iterator

from ..core.exceptions import AmbiguousFactorError, MissingFactorError
from .models import EmissionFactor

__all__ = ["FactorRegistry", "default_seed_path", "illustrative_seed_path"]

#: Packaged published factors (DESNZ 2024 / IPCC 2006) — the product default.
_SEED = Path(__file__).parent / "data" / "published_factors.csv"

#: Illustrative factors, kept for software tests and synthetic demonstrations.
_ILLUSTRATIVE = Path(__file__).parent / "data" / "illustrative_factors.csv"


def default_seed_path() -> Path:
    """Path of the packaged published factor CSV."""
    return _SEED


def illustrative_seed_path() -> Path:
    """Path of the packaged illustrative factor CSV (tests and demos only)."""
    return _ILLUSTRATIVE


def _key(text: str) -> str:
    return "".join(ch for ch in text.strip().lower() if ch.isalnum())


class FactorRegistry:
    """An in-memory emission-factor index with provenance-loaded records."""

    def __init__(self, factors: Iterable[EmissionFactor] = ()) -> None:
        self._factors: dict[str, EmissionFactor] = {}
        for factor in factors:
            self.add(factor)

    # -- construction ------------------------------------------------------ #
    @classmethod
    def from_csv(cls, path: str | Path | None = None) -> "FactorRegistry":
        """Load factors from a CSV whose columns match :class:`EmissionFactor`."""
        source = Path(path) if path is not None else _SEED
        with source.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        registry = cls()
        for row in rows:
            registry.add(_row_to_factor(row, source))
        return registry

    # -- storage ----------------------------------------------------------- #
    def add(self, factor: EmissionFactor) -> None:
        if factor.factor_id in self._factors:
            raise AmbiguousFactorError(
                f"Duplicate factor_id {factor.factor_id!r}; factor IDs must be unique."
            )
        self._factors[factor.factor_id] = factor

    def __len__(self) -> int:
        return len(self._factors)

    def __iter__(self) -> Iterator[EmissionFactor]:
        return iter(self._factors.values())

    def get(self, factor_id: str) -> EmissionFactor:
        try:
            return self._factors[factor_id]
        except KeyError:
            raise MissingFactorError(f"No factor with ID {factor_id!r}.") from None

    # -- catalogue --------------------------------------------------------- #
    def catalogue(self) -> list[dict[str, object]]:
        """Distinct lookup keys in the registry, sorted for display."""
        seen = {
            (f.activity_category, f.substance, f.geography, f.reporting_year, f.gas, f.unit)
            for f in self._factors.values()
        }
        return [
            {
                "category": category,
                "substance": substance,
                "geography": geography,
                "year": year,
                "gas": gas,
                "unit": unit,
            }
            for category, substance, geography, year, gas, unit in sorted(seen)
        ]

    def substances(self, category: str) -> list[str]:
        """Substance keys available for one activity category."""
        wanted = _key(category)
        return sorted({
            f.substance for f in self._factors.values()
            if _key(f.activity_category) == wanted
        })

    # -- resolution -------------------------------------------------------- #
    def find(
        self,
        *,
        activity_category: str,
        substance: str,
        geography: str | None = None,
        year: int | None = None,
        gas: str | None = None,
    ) -> EmissionFactor:
        """Resolve the applicable factor or raise a typed error."""
        category = _key(activity_category)
        material = _key(substance)
        candidates = [
            f for f in self._factors.values()
            if _key(f.activity_category) == category and _key(f.substance) == material
        ]
        if not candidates:
            raise MissingFactorError(
                f"No emission factor for category {activity_category!r}, "
                f"substance {substance!r}."
            )

        # Gas constraint.
        if gas is not None:
            wanted = _key(gas)
            matched = [
                f for f in candidates
                if _key(f.gas) in (wanted, "co2e")
            ]
            if not matched:
                raise MissingFactorError(
                    f"No {gas} factor for {activity_category!r}/{substance!r}."
                )
            # Prefer the gas-specific factor over a combined CO2e factor.
            exact = [f for f in matched if _key(f.gas) == wanted]
            candidates = exact or matched
        else:
            distinct = {_key(f.gas) for f in candidates}
            if len(distinct) > 1:
                gases = ", ".join(sorted({f.gas for f in candidates}))
                raise AmbiguousFactorError(
                    f"{activity_category!r}/{substance!r} has factors for several "
                    f"gases ({gases}); set the activity's gas so the engine can "
                    "select one deterministically."
                )

        # Geography: exact match beats GLOBAL.
        if geography is not None:
            wanted_geo = _key(geography)
            exact_geo = [f for f in candidates if _key(f.geography) == wanted_geo]
            global_geo = [f for f in candidates if _key(f.geography) == "global"]
            if exact_geo:
                candidates = exact_geo
            elif global_geo:
                candidates = global_geo
            else:
                raise MissingFactorError(
                    f"No factor for {activity_category!r}/{substance!r} applicable "
                    f"to geography {geography!r} (no exact or GLOBAL match)."
                )

        # Vintage: newest at or before the reporting year.
        if year is not None:
            at_or_before = [f for f in candidates if f.reporting_year <= year]
            if not at_or_before:
                earliest = min(f.reporting_year for f in candidates)
                raise MissingFactorError(
                    f"No factor for {activity_category!r}/{substance!r} at or "
                    f"before {year}; earliest available vintage is {earliest}."
                )
            newest = max(f.reporting_year for f in at_or_before)
            candidates = [f for f in at_or_before if f.reporting_year == newest]
        else:
            newest = max(f.reporting_year for f in candidates)
            candidates = [f for f in candidates if f.reporting_year == newest]

        if len(candidates) > 1:
            ids = ", ".join(sorted(f.factor_id for f in candidates))
            raise AmbiguousFactorError(
                f"Multiple equally applicable factors for "
                f"{activity_category!r}/{substance!r}: {ids}."
            )
        return candidates[0]


def _row_to_factor(row: dict[str, str], source: Path) -> EmissionFactor:
    """Convert a CSV row into a validated factor (empty optional cells → None)."""
    def opt(name: str) -> str | None:
        raw = (row.get(name) or "").strip()
        return raw if raw else None

    gases_raw = (row.get("gases_covered") or "").strip()
    payload: dict[str, object] = {
        "factor_id": (row.get("factor_id") or "").strip(),
        "activity_category": (row.get("activity_category") or "").strip(),
        "substance": (row.get("substance") or "").strip(),
        "value": float(row.get("value") or "nan"),
        "unit": (row.get("unit") or "").strip(),
        "gas": (row.get("gas") or "").strip(),
        "gases_covered": [g.strip() for g in gases_raw.split(";") if g.strip()],
        "geography": (row.get("geography") or "GLOBAL").strip(),
        "reporting_year": int(row.get("reporting_year") or 0),
        "source_org": (row.get("source_org") or "").strip(),
        "source_reference": (row.get("source_reference") or "").strip(),
        "version": (row.get("version") or "").strip(),
        "uncertainty_pct": float(opt("uncertainty_pct")) if opt("uncertainty_pct") else None,
        "review_status": (row.get("review_status") or "illustrative").strip(),
        "methane_basis": opt("methane_basis"),
        "notes": (row.get("notes") or "").strip(),
    }
    try:
        return EmissionFactor.model_validate(payload)
    except Exception as exc:  # pragma: no cover - error text is the interface
        raise ValueError(f"Invalid factor row in {source.name}: {exc}") from exc
