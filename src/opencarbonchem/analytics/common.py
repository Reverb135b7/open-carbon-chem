"""Shared plumbing for analytics modules.

Re-exported from :mod:`opencarbonchem.core.inventory` so that analytics and
scenarios operate on exactly the same entry type without a cross-dependency.
"""

from ..core.inventory import InventoryEntry, base_rows, validate_entries

__all__ = ["InventoryEntry", "base_rows", "validate_entries"]
