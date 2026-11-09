#!/usr/bin/env python
"""Ecoinvent connector for life-cycle assessment data.

Provides access to the Ecoinvent database for life-cycle assessment factors.

⚠️ IMPORTANT: Ecoinvent is a COMMERCIAL PROPRIETARY DATABASE.
   A valid license from ecoinvent.org is required for legal access.
   This connector implements a stub pattern that ALWAYS falls back
   to synthetic/illustrative data to ensure compliance and avoid
   any claims of unauthorized database access.

   For real Ecoinvent integration, purchase a license at:
   https://ecoinvent.org
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from .base import FactorConnector

logger = logging.getLogger(__name__)


def _parse_version_year(version: str) -> int:
    """Extract the year/numeric part from a version string.

    Handles versions like '2024', '3.9', '3.8', etc.
    """
    # Try to extract leading numeric part
    parts = version.split(".")
    try:
        return int(parts[0])
    except (ValueError, IndexError):
        # Fallback: return a default year
        return 2020


class EcoinventConnector(FactorConnector):
    """Connector for Ecoinvent life-cycle assessment database.

    ⚠️ LEGAL NOTICE: Ecoinvent data is proprietary.
    - A commercial license must be purchased from ecoinvent.org
    - This connector provides a stub pattern that returns synthetic data
    - NEVER attempt to access Ecoinvent databases without a valid license
    - Use of unlicensed Ecoinvent data is copyright infringement

    Data Source: https://ecoinvent.org (commercial license required)
    License: Commercial - Purchase required from ecoinvent.org
    """

    BASE_URL = "https://ecoinvent.org"
    _LICENSE_REQUIRED = True  # Always true - Ecoinvent requires license

    def __init__(self, version: str = "3.9", **kwargs):
        super().__init__(connector_name="Ecoinvent", version=version)
        self.base_url = self.BASE_URL
        self._factors_cache: Optional[list] = None
        self._last_fetched: Optional[datetime] = None
        self._cache_timeout_hours = 24
        self._license_warning_shown = False

        # Show license warning once per session
        if not self._license_warning_shown:
            logger.warning(
                "EcoinventConnector initialized WITHOUT a valid commercial license.\n"
                "This connector returns STUB/ILLUSTRATIVE data only.\n"
                "Purchase a license at https://ecoinvent.org for real access."
            )
            self._license_warning_shown = True

    def fetch_factors(self, **kwargs) -> list:
        """Fetch Ecoinvent factors.

        ⚠️ Always returns stub/illustrative data.
        No real API access is implemented without a valid Ecoinvent license.

        Args:
            **kwargs: Additional parameters (year, category, substance, etc.)

        Returns:
            list[EmissionFactor]: Always returns synthetic/illustrative factors
                with review_status=illustrative and source_org=SYNTHETIC.
        """
        year = kwargs.get("year", _parse_version_year(self.version))

        # Even if API calls were added, they would require a license
        # For now, always use stub data to ensure compliance
        factors = self._get_stub_data(year)

        logger.info(
            f"Ecoinvent factors fetched: {len(factors)} (STUB mode - "
            f"license required for real access)"
        )
        return factors

    def _get_stub_data(self, year: int) -> list:
        """Get Ecoinvent factors via stub implementation.

        Returns illustrated/synthetic factors with proper labeling
        that clearly indicates the license requirement.

        Args:
            year: The year of factors to return

        Returns:
            list of emission factor dicts with stub data
                Always has review_status=illustrative, source_org=SYNTHETIC
        """
        return [
            {
                "substance": "CO2",
                "category": "climate change",
                "value": 0.0,
                "unit": "kgCO2e",
                "year": year,
                "source_org": "SYNTHETIC",
                "review_status": "illustrative",
                "activity_data_type": "estimate",
                "note": "Ecoinvent data requires commercial license from ecoinvent.org",
            }
        ]

    # -- Convenience methods --

    def get_factors_by_category(self, category: str, **kwargs) -> list:
        """Fetch factors by category from Ecoinvent."""
        return self.fetch_factors(**{"category": category, **kwargs})

    def get_factors_by_substance(self, substance: str, **kwargs) -> list:
        """Fetch factors by substance from Ecoinvent."""
        return self.fetch_factors(**{"substance": substance, **kwargs})

    # -- Example/Testing --

    def __repr__(self) -> str:
        return f"<EcoinventConnector version={self.version} stub_mode=True>"

    def __str__(self) -> str:
        return f"Ecoinvent connector v{self.version} (STUB - license required)"


# Example/Testing block
if __name__ == "__main__":
    connector = EcoinventConnector(version="3.9")

    # Test fetch_factors (will always use stub due to license requirement)
    factors = connector.fetch_factors()
    print(f"Ecoinvent factors fetched: {len(factors)}")
    if factors:
        print(f"First factor: {factors[0]}")
    print(f"Source org: {factors[0]['source_org'] if factors else 'N/A'}")
    print(f"Review status: {factors[0]['review_status'] if factors else 'N/A'}")
    print(f"Note: {factors[0].get('note', 'N/A') if factors else 'N/A'}")