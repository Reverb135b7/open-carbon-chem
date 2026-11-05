"""Dimensional unit engine.

Design contract (see ``docs/architecture.md``):

* Every physical quantity carries an explicit :class:`Dimension`.
* Conversions are only permitted between units of identical dimension.
  Crossing dimensions (mass -> energy, volume -> mass) requires an *explicitly
  registered* conversion factor; otherwise :class:`IncompatibleUnitError` is
  raised. The engine never silently applies an incompatible conversion.
* Currency conversion requires an exchange rate supplied deliberately by the
  user; there is no built-in rate for non-USD currencies.

Base dimensions:

===== ==================== ==================
Symbol Meaning             Coherent base unit
===== ==================== ==================
M     mass                 kilogram (kg)
L     length               metre (m)
T     time                 second (s)
E     energy               joule (J)
N     amount of substance  mole (mol)
CUR   money                US dollar (USD)
CNT   count                piece
===== ==================== ==================

Area and volume are powers of length (m2 = L^2, m3 = L^3), so a quantity
built by multiplication (``m * m``) stays dimensionally comparable with the
registered ``m2``/``m3`` units, and all volume units (m3, L, gal, bbl, ...)
share one dimension.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable, Mapping

from .exceptions import CurrencyError, IncompatibleUnitError, UnknownUnitError

__all__ = [
    "BASE_SYMBOLS",
    "DIMENSIONLESS",
    "Dimension",
    "Quantity",
    "Unit",
    "UnitRegistry",
    "convert",
    "default_registry",
    "dimension_of",
    "parse_unit",
    "q",
    "set_default_registry",
]

BASE_SYMBOLS: tuple[str, ...] = ("M", "L", "T", "E", "N", "CUR", "CNT")
BASE_UNIT_NAME: Mapping[str, str] = {
    "M": "kg",
    "L": "m",
    "T": "s",
    "E": "J",
    "N": "mol",
    "CUR": "USD",
    "CNT": "piece",
}

#: Tokens that qualify a mass or volume figure with the substance measured.
#: They are stripped when parsing unit strings because the substance is tracked
#: separately (``EmissionFactor.substance`` / ``gas``).
SUBSTANCE_QUALIFIERS: frozenset[str] = frozenset(
    {
        "co2", "co2e", "ch4", "n2o", "nh3", "nox", "so2", "sox", "voc", "nmvoc",
        "pm10", "pm25", "hfc134a", "hfc32", "hfc125", "sf6", "nf3", "cf4", "c2f6",
        "carbon", "clinker", "steam", "product", "waste", "refuse", "sludge",
        "feedstock", "material", "passenger",
    }
)

_BTU_J = 1055.05585262

# Roots that accept an SI prefix, resolved case-sensitively.
_PREFIXABLE_ROOTS: Mapping[str, tuple[dict[str, Fraction], float]] = {
    "g": ({"M": Fraction(1)}, 1e-3),
    "m": ({"L": Fraction(1)}, 1.0),
    "s": ({"T": Fraction(1)}, 1.0),
    "J": ({"E": Fraction(1)}, 1.0),
    "W": ({"E": Fraction(1), "T": Fraction(-1)}, 1.0),
    "Wh": ({"E": Fraction(1)}, 3600.0),
    "L": ({"L": Fraction(3)}, 1e-3),
    "mol": ({"N": Fraction(1)}, 1.0),
    "var": ({"E": Fraction(1), "T": Fraction(-1)}, 1.0),
}

_PREFIXES: Mapping[str, float] = {
    "da": 1e1, "h": 1e2, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12, "P": 1e15, "E": 1e18,
    "d": 1e-1, "c": 1e-2, "m": 1e-3, "u": 1e-6, "\u00b5": 1e-6, "n": 1e-9, "p": 1e-12,
    "f": 1e-15,
}


# ============================================================================ #
# Dimension
# ============================================================================ #
@dataclass(frozen=True)
class Dimension:
    """A product of base dimensions with rational exponents."""

    exponents: Mapping[str, Fraction]

    def __init__(self, exponents: Mapping[str, int | Fraction | str] | None = None):
        cleaned: dict[str, Fraction] = {}
        for symbol, power in (exponents or {}).items():
            frac = Fraction(str(power))
            if frac == 0:
                continue
            if symbol not in BASE_SYMBOLS:
                raise UnknownUnitError(f"Unknown base dimension symbol {symbol!r}")
            cleaned[symbol] = frac
        object.__setattr__(self, "exponents", dict(sorted(cleaned.items())))

    def __mul__(self, other: "Dimension") -> "Dimension":
        return Dimension(_combine(self.exponents, other.exponents, +1))

    def __truediv__(self, other: "Dimension") -> "Dimension":
        return Dimension(_combine(self.exponents, other.exponents, -1))

    def __pow__(self, power: int | Fraction) -> "Dimension":
        frac = Fraction(str(power))
        return Dimension({k: v * frac for k, v in self.exponents.items()})

    @property
    def is_dimensionless(self) -> bool:
        return not self.exponents

    def is_compatible(self, other: "Dimension") -> bool:
        return self == other

    def __str__(self) -> str:
        if self.is_dimensionless:
            return "1"
        num: list[str] = []
        den: list[str] = []
        for symbol in BASE_SYMBOLS:
            power = self.exponents.get(symbol)
            if power is None:
                continue
            base = BASE_UNIT_NAME[symbol]
            text = base if power == 1 else (base if power == -1 else f"{base}^{power}")
            (num if power > 0 else den).append(text)
        rendered = " ".join(num) or "1"
        if den:
            rendered += "/(" + " ".join(den) + ")"
        return rendered

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Dimension({self})"


def _combine(a: Mapping[str, Fraction], b: Mapping[str, Fraction], sign: int) -> dict[str, Fraction]:
    merged: dict[str, Fraction] = dict(a)
    for symbol, power in b.items():
        total = merged.get(symbol, Fraction(0)) + sign * power
        if total == 0:
            merged.pop(symbol, None)
        else:
            merged[symbol] = total
    return dict(sorted(merged.items()))


DIMENSIONLESS = Dimension()


# ============================================================================ #
# Unit
# ============================================================================ #
@dataclass(frozen=True)
class Unit:
    """A (possibly compound) unit and its scale relative to coherent base units."""

    symbol: str
    dimension: Dimension
    scale: float
    kind: str = "derived"
    note: str | None = None

    def __mul__(self, other: "Unit") -> "Unit":
        return Unit(f"{self.symbol}*{other.symbol}", self.dimension * other.dimension,
                    self.scale * other.scale, kind="derived")

    def __truediv__(self, other: "Unit") -> "Unit":
        return Unit(f"{self.symbol}/{other.symbol}", self.dimension / other.dimension,
                    self.scale / other.scale, kind="derived")

    def __pow__(self, power: int) -> "Unit":
        return Unit(f"{self.symbol}^{power}", self.dimension ** power,
                    self.scale ** power, kind="derived")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Unit):
            return NotImplemented
        return self.dimension == other.dimension and math.isclose(
            self.scale, other.scale, rel_tol=1e-12, abs_tol=1e-15
        )

    def __hash__(self) -> int:
        # Equality is approximate on scale, so hash on dimension only.
        return hash(self.dimension)

    def __str__(self) -> str:
        return self.symbol


# ============================================================================ #
# Registry
# ============================================================================ #
class UnitRegistry:
    """Resolution table for unit symbols, aliases and SI-prefixed roots."""

    def __init__(self, include_defaults: bool = True):
        self._exact: dict[str, Unit] = {}
        self._alias: dict[str, Unit] = {}
        self._memo: dict[str, Unit] = {}
        if include_defaults:
            self.register_defaults()

    def register(self, symbol: str, dimension: Dimension | Mapping[str, int | Fraction],
                 scale: float, *, kind: str = "custom", aliases: Iterable[str] = (),
                 note: str | None = None) -> Unit:
        dim = dimension if isinstance(dimension, Dimension) else Dimension(dimension)
        unit = Unit(symbol, dim, float(scale), kind=kind, note=note)
        self._exact[symbol] = unit
        self._memo[symbol] = unit
        for alias in aliases:
            self._alias[_norm(alias)] = unit
            self._alias[_norm(symbol)] = unit
        return unit

    def register_defaults(self) -> None:
        reg = self.register
        # -- mass -----------------------------------------------------------
        reg("kg", {"M": 1}, 1.0, kind="base", aliases=["kilogram", "kilograms", "kilos"])
        reg("t", {"M": 1}, 1000.0, aliases=["tonne", "tonnes", "metric ton", "metricton", "tonneus"],
            note="metric tonne = 1000 kg; the ambiguous spelling 'ton' is deliberately rejected")
        reg("kt", {"M": 1}, 1e6, aliases=["kilotonne", "kiloton"])
        reg("Mt", {"M": 1}, 1e9, aliases=["megatonne", "million tonnes"])
        reg("Gt", {"M": 1}, 1e12, aliases=["gigatonne"])
        reg("short_tn", {"M": 1}, 907.18474, aliases=["US ton", "short ton", "short tons"])
        reg("long_tn", {"M": 1}, 1016.0469088, aliases=["UK ton", "long ton", "long tons"])
        reg("lb", {"M": 1}, 0.45359237, aliases=["lbs", "pound", "pounds"])
        reg("oz", {"M": 1}, 0.028349523125, aliases=["ounce", "ounces"])
        # -- length / area --------------------------------------------------
        reg("m", {"L": 1}, 1.0, kind="base", aliases=["metre", "meter", "metres", "meters"])
        reg("km", {"L": 1}, 1000.0, aliases=["kilometre", "kilometer", "kilometres"])
        reg("mi", {"L": 1}, 1609.344, aliases=["mile", "miles"])
        reg("nmi", {"L": 1}, 1852.0, aliases=["nautical mile", "nautical miles"])
        reg("ft", {"L": 1}, 0.3048, aliases=["foot", "feet"])
        reg("yd", {"L": 1}, 0.9144, aliases=["yard", "yards"])
        reg("m2", {"L": 2}, 1.0, kind="base", aliases=["sqm", "square metre", "square meter"])
        reg("ha", {"L": 2}, 1e4, aliases=["hectare", "hectares"])
        reg("km2", {"L": 2}, 1e6, aliases=["square kilometre", "square kilometer"])
        # -- volume ---------------------------------------------------------
        reg("m3", {"L": 3}, 1.0, kind="base", aliases=["cum", "cubic metre", "cubic meter", "sm3", "SM3", "Nm3"])
        reg("L", {"L": 3}, 1e-3, aliases=["litre", "liter", "litres", "liters"])
        reg("ft3", {"L": 3}, 0.028316846592, aliases=["cf", "cubic foot", "cubic feet"])
        reg("scf", {"L": 3}, 0.028316846592, aliases=["Mcf", "kcf"],
            note="standard cubic foot, 15 C / 101.325 kPa; Mcf = 1000 scf registered separately below")
        reg("Mcf", {"L": 3}, 28.316846592, note="1000 standard cubic feet")
        reg("gal", {"L": 3}, 3.785411784e-3, aliases=["gallon", "gallons", "US gal", "US gallon"])
        reg("bbl", {"L": 3}, 0.158987294928, aliases=["barrel", "barrels", "boe", "stb"],
            note="stock-tank barrel = 158.987 L")
        # -- time -----------------------------------------------------------
        reg("s", {"T": 1}, 1.0, kind="base", aliases=["sec", "second", "seconds"])
        reg("min", {"T": 1}, 60.0, aliases=["minute", "minutes"])
        reg("h", {"T": 1}, 3600.0, aliases=["hr", "hour", "hours"])
        reg("d", {"T": 1}, 86400.0, aliases=["day", "days"])
        reg("a", {"T": 1}, 31_557_600.0, aliases=["yr", "year", "years"], note="Julian year = 365.25 d")
        # -- energy ---------------------------------------------------------
        reg("J", {"E": 1}, 1.0, kind="base", aliases=["joule", "joules"])
        reg("Wh", {"E": 1}, 3600.0, aliases=["watt-hour", "watt hour", "watthour"])
        reg("Btu", {"E": 1}, _BTU_J, aliases=["btu"], note="International Table Btu")
        reg("MMBtu", {"E": 1}, 1e6 * _BTU_J, aliases=["MBtu", "mmBtu", "million Btu"])
        reg("therm", {"E": 1}, 1e5 * _BTU_J, aliases=["therms"])
        reg("toe", {"E": 1}, 41.868e9, aliases=["tonne of oil equivalent", "ktoe_dummy"],
            note="1 toe = 41.868 GJ (IEA convention)")
        # -- amount / count / money ----------------------------------------
        reg("mol", {"N": 1}, 1.0, kind="base", aliases=["mole", "moles"])
        reg("piece", {"CNT": 1}, 1.0, kind="base",
            aliases=["unit", "units", "each", "pce", "vehicle", "trip", "shipment", "item", "seat", "ton_km_packet"])
        reg("USD", {"CUR": 1}, 1.0, kind="base", aliases=["$", "us$", "dollar", "dollars", "usd"])
        # -- composite transport units -------------------------------------
        reg("tkm", {"M": 1, "L": 1}, 1000.0, aliases=["tonne-km", "tonne km", "ton-km", "tkm"],
            note="tonne kilometre = 1000 kg*m")
        reg("pkm", {"CNT": 1, "L": 1}, 1000.0, aliases=["passenger-km", "passenger km", "pkm"],
            note="passenger kilometre = 1000 piece*m")
        reg("tonmi", {"M": 1, "L": 1}, 907.18474 * 1609.344, aliases=["ton-mile", "ton mile"])

    # -- resolution ---------------------------------------------------------
    def unit(self, symbol: str) -> Unit:
        """Resolve a single (uncompounded) symbol, including SI-prefixed roots."""
        key = symbol.strip()
        if key in self._exact:
            return self._exact[key]
        if key in self._memo:
            return self._memo[key]
        lowered = _norm(key)
        if lowered in self._alias:
            return self._alias[lowered]
        resolved = self._resolve_prefixed(key)
        if resolved is not None:
            self._memo[key] = resolved
            return resolved
        if lowered == "ton":
            raise UnknownUnitError(
                "'ton' is ambiguous (metric tonne, short ton or long ton?). Use 't', 'short_tn' or 'long_tn'."
            )
        raise UnknownUnitError(
            f"Unit {symbol!r} is not registered. Register it explicitly or correct the unit string."
        )

    def _resolve_prefixed(self, symbol: str) -> Unit | None:
        for prefix, factor in _PREFIXES.items():
            if not symbol.startswith(prefix):
                continue
            root = symbol[len(prefix):]
            entry = _PREFIXABLE_ROOTS.get(root)
            if entry is None:
                continue
            dims, root_scale = entry
            return Unit(symbol, Dimension(dims), root_scale * factor, kind="prefixed")
        return None

    def configure_exchange_rates(self, rates_to_usd: Mapping[str, float]) -> None:
        """Register non-USD currencies. Never called with built-in defaults."""
        for symbol, rate in rates_to_usd.items():
            if rate <= 0:
                raise CurrencyError(f"Exchange rate for {symbol} must be positive, got {rate}")
            self.register(symbol, {"CUR": 1}, float(rate),
                          note=f"explicit exchange rate: 1 {symbol} = {rate} USD")

    def parse(self, expression: str) -> Unit:
        return parse_unit(expression, self)

    def known(self) -> list[str]:
        return sorted(set(self._exact) | set(self._alias.values().__iter__().__self.__len__() and set()))

    def symbols(self) -> list[str]:
        return sorted(self._exact)


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-\u00b7./]", "", text).lower()


# ============================================================================ #
# Parsing compound expressions
# ============================================================================ #
_ATOM = re.compile(r"([A-Za-z\u00b5][A-Za-z0-9_\u00b5]*)(?:\^(-?\d+))?")


def parse_unit(expression: str, registry: UnitRegistry | None = None) -> Unit:
    """Parse expressions such as ``kg CO2/GJ``, ``t/TJ``, ``g CH4/kWh``, ``t*km``."""
    registry = registry or default_registry()
    raw = (expression or "").strip()
    if not raw:
        raise UnknownUnitError("Empty unit expression")

    normalised = raw.replace("\u2044", "/").replace(" per ", "/")
    parts = [p for p in normalised.split("/")]
    if len(parts) > 3:
        raise UnknownUnitError(f"Cannot parse unit expression {raw!r}: too many '/' separators")

    unit = _parse_product(parts[0], registry, raw)
    for denom in parts[1:]:
        unit = unit / _parse_product(denom, registry, raw)
    display = _pretty(raw)
    return Unit(display, unit.dimension, unit.scale, kind="parsed", note=raw)


def _parse_product(text: str, registry: UnitRegistry, original: str) -> Unit:
    cleaned = text
    for qualifier in sorted(SUBSTANCE_QUALIFIERS, key=len, reverse=True):
        cleaned = re.sub(rf"(?<![A-Za-z0-9]){re.escape(qualifier)}(?![A-Za-z0-9])", " ", cleaned,
                         flags=re.IGNORECASE)
    cleaned = re.sub(r"[*\u00b7]", " ", cleaned)
    result: Unit | None = None
    for match in _ATOM.finditer(cleaned):
        symbol, exponent = match.group(1), match.group(2)
        base = registry.unit(symbol)
        factor = base ** int(exponent) if exponent else base
        result = factor if result is None else result * factor
    if result is None:
        return Unit("1", DIMENSIONLESS, 1.0, kind="parsed")
    return result


def _pretty(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


# ============================================================================ #
# Quantity
# ============================================================================ #
@dataclass(frozen=True)
class Quantity:
    """A numeric value bound to a unit. Arithmetic always preserves dimensions."""

    value: float
    unit: Unit
    label: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TypeError(f"Quantity value must be numeric, got {self.value!r}")
        if math.isnan(self.value):
            raise ValueError("Quantity value must not be NaN")
        if not math.isfinite(self.value):
            raise ValueError("Quantity value must be finite")
        object.__setattr__(self, "value", float(self.value))
        if isinstance(self.unit, str):
            object.__setattr__(self, "unit", default_registry().parse(self.unit))

    @classmethod
    def of(cls, value: float, unit: str | Unit, label: str | None = None) -> "Quantity":
        resolved = default_registry().parse(unit) if isinstance(unit, str) else unit
        return cls(float(value), resolved, label)

    # -- properties ---------------------------------------------------------
    @property
    def dimension(self) -> Dimension:
        return self.unit.dimension

    @property
    def base_value(self) -> float:
        return self.value * self.unit.scale

    @property
    def magnitude(self) -> float:
        return abs(self.value)

    def is_zero(self, tol: float = 1e-15) -> bool:
        return abs(self.base_value) <= tol

    def is_negative(self) -> bool:
        return self.value < 0

    # -- conversion ---------------------------------------------------------
    def to(self, target: str | Unit) -> "Quantity":
        resolved = default_registry().parse(target) if isinstance(target, str) else target
        if resolved.dimension != self.unit.dimension:
            raise IncompatibleUnitError(
                f"Cannot convert {self.unit.dimension} ({self.unit.symbol}) to "
                f"{resolved.dimension} ({resolved.symbol}); a registered conversion factor is required."
            )
        return Quantity(self.value * (self.unit.scale / resolved.scale), resolved, self.label)

    def converts_to(self, target: str | Unit) -> bool:
        try:
            resolved = default_registry().parse(target) if isinstance(target, str) else target
        except UnknownUnitError:
            return False
        return resolved.dimension == self.unit.dimension

    # -- arithmetic ---------------------------------------------------------
    def _require_same_dimension(self, other: "Quantity", op: str) -> None:
        if other.dimension != self.dimension:
            raise IncompatibleUnitError(
                f"Cannot {op} a {self.unit.dimension} quantity with a {other.unit.dimension} quantity"
            )

    def __add__(self, other: "Quantity") -> "Quantity":
        self._require_same_dimension(other, "add")
        return Quantity(self.base_value + other.base_value, _coherent_unit(self.dimension), self.label)

    def __sub__(self, other: "Quantity") -> "Quantity":
        self._require_same_dimension(other, "subtract")
        return Quantity(self.base_value - other.base_value, _coherent_unit(self.dimension), self.label)

    def __mul__(self, other: "Quantity | float") -> "Quantity":
        if isinstance(other, Quantity):
            return Quantity(self.base_value * other.base_value, self.unit * other.unit, self.label)
        return Quantity(self.base_value * float(other), self.unit, self.label)

    def __rmul__(self, other: float) -> "Quantity":
        return self.__mul__(other)

    def __truediv__(self, other: "Quantity | float") -> "Quantity":
        if isinstance(other, Quantity):
            if other.is_zero():
                raise ZeroDivisionError("Division by a zero quantity")
            return Quantity(self.base_value / other.base_value, self.unit / other.unit, self.label)
        if float(other) == 0:
            raise ZeroDivisionError("Division by zero")
        return Quantity(self.base_value / float(other), self.unit, self.label)

    def __neg__(self) -> "Quantity":
        return Quantity(-self.value, self.unit, self.label)

    def __abs__(self) -> "Quantity":
        return Quantity(abs(self.value), self.unit, self.label)

    def __lt__(self, other: "Quantity") -> bool:
        self._require_same_dimension(other, "compare")
        return self.base_value < other.base_value

    def __le__(self, other: "Quantity") -> bool:
        self._require_same_dimension(other, "compare")
        return self.base_value <= other.base_value

    def __str__(self) -> str:
        text = f"{self.value:g} {self.unit.symbol}"
        return f"{text} [{self.label}]" if self.label else text

    def __repr__(self) -> str:  # pragma: no cover
        return f"Quantity({self.value!r}, {self.unit.symbol!r})"


def _coherent_unit(dimension: Dimension) -> Unit:
    unit = Unit("1", DIMENSIONLESS, 1.0)
    for symbol, power in dimension.exponents.items():
        if power.denominator != 1:
            raise IncompatibleUnitError(f"Cannot build coherent unit for fractional exponent {power}")
        unit = unit * Unit(BASE_UNIT_NAME[symbol], Dimension({symbol: 1}), 1.0) ** int(power)
    return unit


# ============================================================================ #
# Module helpers
# ============================================================================ #
_DEFAULT_REGISTRY: UnitRegistry | None = None


def default_registry() -> UnitRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = UnitRegistry()
    return _DEFAULT_REGISTRY


def set_default_registry(registry: UnitRegistry) -> None:
    """Install ``registry`` as the process default (tests, app configuration)."""
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = registry


def q(value: float, unit: str, label: str | None = None) -> Quantity:
    """Shorthand: ``q(56.1, "kg CO2/GJ")``."""
    return Quantity.of(value, unit, label)


def convert(quantity: Quantity, target: str) -> Quantity:
    return quantity.to(target)


def dimension_of(unit: str) -> Dimension:
    return default_registry().parse(unit).dimension
