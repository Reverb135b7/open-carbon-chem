"""Connectors for various emission factor databases.

Provides access to DEFRA, EPA, and Ecoinvent emission factor databases
through a unified interface.
"""

from .base import FactorConnector, CacheManager
from .defra import DefraConnector
from .epa import EPAConnector
from .ecoinvent import EcoinventConnector

__all__ = [
    "FactorConnector",
    "CacheManager",
    "DefraConnector",
    "EPAConnector",
    "EcoinventConnector",
]


def get_connector(name: str, **kwargs):
    """Get a connector instance by name.

    Args:
        name: The connector name ('defra', 'epa', 'ecoinvent')
        **kwargs: Additional arguments to pass to the connector constructor

    Returns:
        A connector instance of the specified type.
    """
    connectors = {
        "defra": DefraConnector,
        "epa": EPAConnector,
        "ecoinvent": EcoinventConnector,
    }
    connector_class = connectors.get(name.lower())
    if connector_class is None:
        raise ValueError(f"Unknown connector: {name}. Available: {list(connectors.keys())}")
    return connector_class(**kwargs)