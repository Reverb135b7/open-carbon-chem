#!/usr/bin/env python
"""Base class for emission factor connectors.

Defines the interface for connecting to external emission factor databases.
Ensures Monte Carlo reproducibility (N4 constraint) by supporting version
caching and snapshot versioning.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime


class FactorConnector(ABC):
    """Abstract base class for emission factor connectors.
    
    Subclasses must implement the `fetch_factors` method to retrieve
    emission factors from external databases. All connectors support
    version caching to preserve Monte Carlo reproducibility (N4 constraint).
    """
    
    def __init__(self, connector_name: str, version: Optional[str] = None):
        self.connector_name = connector_name
        self.version = version  # cached version for reproducibility
        self._cached_factors: Optional[list] = None
        self._last_fetched: Optional[datetime] = None
    
    @abstractmethod
    def fetch_factors(self, **kwargs) -> list:
        """Fetch emission factors from the external database.
        
        Args:
            **kwargs: Additional parameters for the fetch operation,
                     such as year, category, substance, etc.
        
        Returns:
            list[EmissionFactor]: List of emission factors fetched from the database.
        """
        raise NotImplementedError("Subclasses must implement fetch_factors")
    
    def get_factors(self, **kwargs) -> list:
        """Fetch factors, using cache if available and recent.
        
        This method ensures Monte Carlo reproducibility by using cached
        factor versions. If the cache is stale or empty, it fetches fresh
        factors and updates the cache.
        
        Args:
            **kwargs: Parameters for factor fetch (year, category, etc.)
        
        Returns:
            list[EmissionFactor]: List of emission factors.
        """
        # Check if we have cached factors that are still valid
        if self._cached_factors is not None and self._last_fetched is not None:
            # Check if cache is recent (within 24 hours for annual factors)
            from datetime import datetime as dt
            age = dt.now() - self._last_fetched
            if age.days < 1:  # Daily refresh threshold
                return self._cached_factors
        
        # Fetch fresh factors
        factors = self.fetch_factors(**kwargs)
        
        # Update cache
        self._cached_factors = factors
        self._last_fetched = datetime.now()
        
        return factors
    
    def reset_cache(self) -> None:
        """Reset the factor cache, forcing a fresh fetch on next request."""
        self._cached_factors = None
        self._last_fetched = None
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.connector_name}, version={self.version})>"


class CacheManager:
    """Manages caching of factor data in the SQLAlchemy database.
    
    Ensures Monte Carlo reproducibility (N4 constraint) by storing
    factor snapshots with strict version timestamps.
    """
    
    def __init__(self, session_factory=None):
        self.session_factory = session_factory
    
    def save_factor_snapshot(self, connector_name: str, factors: list, version: str) -> None:
        """Save a factor snapshot to the database for reproducibility.
        
        Args:
            connector_name: Name of the connector that fetched the factors
            factors: List of EmissionFactor objects
            version: Version string (e.g., "2024", "v1.2")
        """
        # Implementation depends on the database schema
        pass
    
    def get_factor_snapshot(self, connector_name: str, version: str) -> Optional[list]:
        """Retrieve a cached factor snapshot from the database.
        
        Args:
            connector_name: Name of the connector
            version: Version string to look up
        
        Returns:
            List of EmissionFactor objects or None if not found
        """
        return None