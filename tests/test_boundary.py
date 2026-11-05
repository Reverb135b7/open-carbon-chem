"""Organisational boundary tests: validation, consolidation, documentation."""

import pytest

from opencarbonchem.accounting import BoundaryEntity, OrganisationalBoundary
from opencarbonchem.core.exceptions import BoundaryError


def _boundary(method: str = "operational_control") -> OrganisationalBoundary:
    return OrganisationalBoundary(
        org_id="ORG-TEST",
        name="Test Chemicals Ltd",
        method=method,
        entities=(
            BoundaryEntity("ENT-A", "Owned plant A", equity_share=0.6, geography="GB"),
            BoundaryEntity("ENT-B", "JV plant B", equity_share=1.0, geography="FR"),
        ),
        notes="SYNTHETIC test boundary",
    )


@pytest.mark.unit
def test_documented_boundary_construction():
    boundary = _boundary()
    assert boundary.method == "operational_control"
    assert len(boundary.entities) == 2


@pytest.mark.unit
def test_control_consolidation_ignores_equity_share():
    # Operational control reports 100% of controlled entities regardless of share.
    boundary = _boundary(method="operational_control")
    assert boundary.weight_for("ENT-A") == 1.0
    assert boundary.weight_for("ENT-B") == 1.0
    # Hand check: 2000 + 1000 kg = 3000 kg.
    assert boundary.consolidate({"ENT-A": 2000.0, "ENT-B": 1000.0}) == pytest.approx(3000.0)


@pytest.mark.unit
def test_equity_share_consolidation_hand_computed():
    boundary = _boundary(method="equity_share")
    assert boundary.weight_for("ENT-A") == 0.6
    # Hand check: 2000 × 0.6 + 1000 × 1.0 = 2200 kg.
    assert boundary.consolidate({"ENT-A": 2000.0, "ENT-B": 1000.0}) == pytest.approx(2200.0)


@pytest.mark.unit
def test_financial_control_consolidates_at_full_share():
    boundary = _boundary(method="financial_control")
    assert boundary.consolidate({"ENT-A": 2000.0, "ENT-B": 1000.0}) == pytest.approx(3000.0)


@pytest.mark.unit
def test_consolidation_requires_every_boundary_entity():
    boundary = _boundary()
    with pytest.raises(BoundaryError) as exc:
        boundary.consolidate({"ENT-A": 2000.0})
    assert "ENT-B" in str(exc.value)
    # Explicit zero is allowed.
    assert boundary.consolidate({"ENT-A": 2000.0, "ENT-B": 0.0}) == pytest.approx(2000.0)


@pytest.mark.unit
def test_consolidation_rejects_entities_outside_boundary():
    boundary = _boundary()
    with pytest.raises(BoundaryError) as exc:
        boundary.consolidate({"ENT-A": 1.0, "ENT-B": 1.0, "ENT-X": 5.0})
    assert "ENT-X" in str(exc.value)


@pytest.mark.unit
def test_consolidation_rejects_negative_emissions():
    boundary = _boundary()
    with pytest.raises(BoundaryError):
        boundary.consolidate({"ENT-A": -1.0, "ENT-B": 1.0})


@pytest.mark.unit
@pytest.mark.parametrize(
    "kwargs",
    [
        {"org_id": "", "name": "X", "method": "operational_control",
         "entities": (BoundaryEntity("ENT-1", "One"),)},
        {"org_id": "ORG", "name": "X", "method": "whatever",
         "entities": (BoundaryEntity("ENT-1", "One"),)},
        {"org_id": "ORG", "name": "X", "method": "operational_control",
         "entities": ()},
    ],
)
def test_invalid_boundary_definitions_are_rejected(kwargs):
    with pytest.raises(BoundaryError):
        OrganisationalBoundary(**kwargs)


@pytest.mark.unit
def test_duplicate_entity_ids_rejected():
    with pytest.raises(BoundaryError) as exc:
        OrganisationalBoundary(
            org_id="ORG-2",
            name="X",
            method="operational_control",
            entities=(
                BoundaryEntity("ENT-1", "One"),
                BoundaryEntity("ENT-1", "Copy"),
            ),
        )
    assert "ENT-1" in str(exc.value)


@pytest.mark.unit
@pytest.mark.parametrize("share", [0.0, -0.1, 1.5])
def test_invalid_equity_share_rejected(share):
    with pytest.raises(BoundaryError):
        BoundaryEntity("ENT-1", "One", equity_share=share)


@pytest.mark.unit
def test_unknown_entity_weight_lookup():
    boundary = _boundary()
    with pytest.raises(BoundaryError):
        boundary.weight_for("ENT-NOPE")


@pytest.mark.unit
def test_boundary_documentation_payload():
    # Handover §7: the boundary must be documentable for the report appendix.
    boundary = _boundary(method="equity_share")
    document = boundary.document()
    assert document["org_id"] == "ORG-TEST"
    assert document["method"] == "equity_share"
    assert document["notes"] == "SYNTHETIC test boundary"
    assert len(document["entities"]) == 2
    first = document["entities"][0]
    assert first["entity_id"] == "ENT-A"
    assert first["equity_share"] == 0.6
    assert first["reporting_weight"] == 0.6  # equity method weights by share
    assert first["geography"] == "GB"
