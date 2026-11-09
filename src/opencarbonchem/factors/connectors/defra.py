#!/usr/bin/env python
"""DEFRA (UK Department for Business, Energy & Security) emission factor connector.

Provides access to the UK Government GHG Conversion Factors for Company Reporting.
"""

from __future__ import annotations

import os
import logging
from typing import Optional

try:  # optional: the connectors ship stub data when `requests` is unavailable
    import requests
except ImportError:  # pragma: no cover - exercised only in minimal installs
    requests = None
from datetime import datetime

from .base import FactorConnector


logger = logging.getLogger(__name__)


class DefraConnector(FactorConnector):
    """Connector for UK DEFRA GHG Conversion Factors.

    Accesses the UK Government GHG Conversion Factors for Company Reporting database.
    Provides factors for Scope 1, 2, and 3 emissions.

    Data Source: https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting
    License: Open Government Licence - Free for non-commercial use with attribution
    """

    BASE_URL = "https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting"
    FACTOR_DATA_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data",
        "defra_factors illustrative.csv",
    )

    def __init__(self, version: str = "2024", **kwargs):
        super().__init__(connector_name="DEFRA", version=version)
        self.base_url = self.BASE_URL
        self._factors_cache: Optional[list] = None
        self._last_fetched: Optional[datetime] = None
        self._cache_timeout_hours = 24

    def fetch_factors(self, **kwargs) -> list:
        """Fetch DEFRA emission factors for the specified year.

        Tries real API first, falls back to stub implementation.
        In production, this would connect to the DEFRA API and parse
        the response for emission factors.

        Args:
            **kwargs: Additional parameters (year, category, substance, etc.)

        Returns:
            list[EmissionFactor]: List of emission factors from DEFRA database.
                Returns stub data if API unavailable.
        """
        year = kwargs.get("year", int(self.version))

        # Try real API first
        try:
            factors = self._fetch_factors_from_api(year) if requests is not None else None
            if factors is not None:
                self._factors_cache = factors
                self._last_fetched = datetime.now()
                logger.info(f"Fetched {len(factors)} DEFRA factors for year={year} via API")
                return factors
        except Exception as e:
            logger.warning(f"DEFRA API fetch failed: {e}; falling back to stub data")

        # Fall back to stub/cached data
        return self._get_stub_data(year)

    def _fetch_factors_from_api(self, year: int) -> Optional[list]:
        """Fetch factors from real DEFRA API.

        Returns None if API unavailable (network error, 404, etc.)
        Returns list of factors if successful.
        """
        # Construct the API URL
        url = f"{self.base_url}/{year}/"

        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                # Parse the factors from the response
                # Format depends on DEFRA's actual response structure
                # This is a stub parse - real implementation would parse HTML/JSON
                logger.info(f"DEFRA API returned 200 for year={year}")
                # For now, return None to trigger stub fallback
                # Real implementation would parse response.text here
                return None  # Stub fallback
            else:
                logger.warning(f"DEFRA API returned status {response.status_code} for year={year}")
                return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"DEFRA API network error: {e}")
            return None
        except Exception as e:
            logger.warning(f"DEFRA API unexpected error: {e}")
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
        # Import here to avoid circular imports at module level
        import pandas as pd

        # Try to load illustrative factor data file if it exists
        factors: list = []

        # Check if illustrative data file exists
        illustrative_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "illustrative_factors.csv",
        )

        if os.path.exists(illustrative_path):
            try:
                df = pd.read_csv(illustrative_path)
                # Filter by year if column exists
                if "year" in df.columns:
                    df = df[df["year"] == year]
                # Convert to factor list format
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
                logger.info(f"Loaded {len(factors)} illustrative DEFRA factors from file for year={year}")
            except Exception as e:
                logger.warning(f"Failed to load illustrative factors from file: {e}")
                factors = self._minimal_stub_factors(year)
        else:
            # No file available - use minimal stub
            factors = self._minimal_stub_factors(year)

        return factors

    def _minimal_stub_factors(self, year: int) -> list:
        """Minimal stub: return a basic factor for the given year.

        Always returns data with review_status=illustrative and
        source_org=SYNTHETIC to maintain integrity.
        """
        # No live source and no packaged file: return nothing rather than a
        # placeholder number that could be mistaken for a real factor.
        logger.info("No live DEFRA factors available; returning an empty stub set.")
        return []

    # -- Convenience methods --

    def get_factors_by_category(
        self, category: str, year: Optional[int] = None
    ) -> list:
        """Fetch factors for a specific category.

        Args:
            category: The emission factor category (e.g., 'scope1', 'scope3')
            year: The year of the factors (default: connector version year)

        Returns:
            list[EmissionFactor]: List of emission factors for the category.
        """
        year = year if year is not None else int(self.version)
        return self.fetch_factors(year=year, category=category)

    def get_factors_by_substance(self, substance: str, **kwargs) -> list:
        """Fetch factors for a specific substance.

        Args:
            substance: The substance name (e.g., 'CO2', 'NOx', 'CH4')
            **kwargs: Additional parameters (year, category, etc.)

        Returns:
            list[EmissionFactor]: List of emission factors for the substance.
        """
        return self.fetch_factors(**{"substance": substance, **kwargs})

    # -- Example/Testing --

    def __repr__(self) -> str:
        return f"<DefraConnector version={self.version} factors_cached={self._factors_cache is not None}>"

    def __str__(self) -> str:
        return f"DEFRA connector v{self.version} (illustrative data: {self._factors_cache is not None})"


# Example/Testing block
if __name__ == "__main__":
    connector = DefraConnector(version="2024")

    # Test fetch_factors (will use stub if API unavailable)
    factors = connector.fetch_factors()
    print(f"DEFRA factors fetched: {len(factors)}")
    if factors:
        print(f"First factor: {factors[0]}")
    print(f"Source org: {factors[0]['source_org'] if factors else 'N/A'}")
    print(f"Review status: {factors[0]['review_status'] if factors else 'N/A'}")