#!/usr/bin/env python
"""EPA (Environmental Protection Agency) emission factor connector.

Provides access to the EPA's Emission Factor Repository (AP-42).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

try:  # optional: the connectors ship stub data when `requests` is unavailable
    import requests
except ImportError:  # pragma: no cover - exercised only in minimal installs
    requests = None
from datetime import datetime

from .base import FactorConnector

logger = logging.getLogger(__name__)


class EPAConnector(FactorConnector):
    """Connector for US EPA Emission Factor Database (AP-42).

    Accesses the EPA's emission factor database for criteria pollutants
    and greenhouse gases.

    Data Source: https://www.epa.gov/air-emissions-factor-db
    License: Public domain - US Government work
    """

    BASE_URL = "https://www.epa.gov/air-emissions-factor-db"
    FACTOR_DATA_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "epa_factors illustrative.csv",
    )

    def __init__(self, version: str = "2023", **kwargs):
        super().__init__(connector_name="EPA", version=version)
        self.base_url = self.BASE_URL
        self._factors_cache: Optional[list] = None
        self._last_fetched: Optional[datetime] = None
        self._cache_timeout_hours = 24

    def fetch_factors(self, **kwargs) -> list:
        """Fetch EPA emission factors.

        Tries real API first, falls back to stub implementation.
        In production, this would connect to the EPA API and parse
        the response for emission factors.

        Args:
            **kwargs: Additional parameters (year, category, substance, etc.)

        Returns:
            list[EmissionFactor]: List of emission factors from EPA database.
                Returns stub data if API unavailable.
        """
        year = kwargs.get("year", int(self.version))

        # Try real API first
        try:
            factors = self._fetch_factors_from_api(year) if requests is not None else None
            if factors is not None:
                self._factors_cache = factors
                self._last_fetched = datetime.now()
                logger.info(f"Fetched {len(factors)} EPA factors for year={year} via API")
                return factors
        except Exception as e:
            logger.warning(f"EPA API fetch failed: {e}; falling back to stub data")

        # Fall back to stub/cached data
        return self._get_stub_data(year)

    def _fetch_factors_from_api(self, year: int) -> Optional[list]:
        """Fetch factors from real EPA API.

        Returns None if API unavailable (network error, 404, etc.)
        Returns list of factors if successful.
        """
        # Construct search URL - EPA AP-42 has multiple endpoints
        # This is a generic search; real implementation would use proper EPA API params
        url = f"{self.base_url}/"

        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                logger.info(f"EPA API returned 200 for year={year}")
                # Real implementation would parse response.text
                # For now, return None to trigger stub fallback
                return None
            else:
                logger.warning(f"EPA API returned status {response.status_code} for year={year}")
                return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"EPA API network error: {e}")
            return None
        except Exception as e:
            logger.warning(f"EPA API unexpected error: {e}")
            return None

    def _get_stub_data(self, year: int) -> list:
        """Get emission factors via stub implementation.

        Returns illustrated/synthetic factors with proper labeling.
        This ensures the system always works, even without network access.

        Args:
            year: The year of factors to return

        Returns:
            list of emission factor dicts with stub data
        """
        import pandas as pd

        # Try to load illustrative factor data file if it exists
        factors: list = []

        illustrative_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "epa_factors illustrative.csv",
        )

        if os.path.exists(illustrative_path):
            try:
                df = pd.read_csv(illustrative_path)
                if "year" in df.columns:
                    df = df[df["year"] == year]
                for _, row in df.iterrows():
                    factor = {
                        "substance": row.get("substance", "unknown"),
                        "category": row.get("category", "unknown"),
                        "value": row.get("value", 0.0),
                        "unit": row.get("unit", "kgCO2e"),
                        "year": year,
                        "source_org": "SYNTHETIC",
                        "review_status": "illustrative",
                        "activity_data_type": row.get("data_type", "unknown"),
                    }
                    factors.append(factor)
                logger.info(f"Loaded {len(factors)} illustrative EPA factors from file for year={year}")
            except Exception as e:
                logger.warning(f"Failed to load illustrative factors from file: {e}")
                factors = self._minimal_stub_factors(year)
        else:
            factors = self._minimal_stub_factors(year)

        return factors

    def _minimal_stub_factors(self, year: int) -> list:
        """Minimal stub: return a basic factor for the given year."""
        return [
            {
                "substance": "CO2",
                "category": "purchased_electricity",
                "value": 0.0,
                "unit": "kgCO2e",
                "year": year,
                "source_org": "SYNTHETIC",
                "review_status": "illustrative",
                "activity_data_type": "estimate",
            }
        ]

    # -- Convenience methods --

    def get_factors_by_substance(self, substance: str, **kwargs) -> list:
        """Fetch factors for a specific substance."""
        return self.fetch_factors(**{"substance": substance, **kwargs})

    def get_factors_by_category(self, category: str, **kwargs) -> list:
        """Fetch factors by category."""
        return self.fetch_factors(**{"category": category, **kwargs})

    # -- Example/Testing --

    def __repr__(self) -> str:
        return f"<EPAConnector version={self.version} factors_cached={self._factors_cache is not None}>"

    def __str__(self) -> str:
        return f"EPA connector v{self.version} (illustrative data: {self._factors_cache is not None})"


# Example/Testing block
if __name__ == "__main__":
    connector = EPAConnector(version="2023")

    # Test fetch_factors (will use stub if API unavailable)
    factors = connector.fetch_factors()
    print(f"EPA factors fetched: {len(factors)}")
    if factors:
        print(f"First factor: {factors[0]}")
    print(f"Source org: {factors[0]['source_org'] if factors else 'N/A'}")
    print(f"Review status: {factors[0]['review_status'] if factors else 'N/A'}")