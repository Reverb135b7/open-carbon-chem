"""Emission factor database: provenance model, registry and seed data."""

from .models import EmissionFactor
from .registry import FactorRegistry, default_seed_path

__all__ = ["EmissionFactor", "FactorRegistry", "default_seed_path"]
