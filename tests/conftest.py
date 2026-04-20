# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""Shared test fixtures for WateringHub."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_valves():
    """Return valve config as stored in .storage."""
    return {
        "valve_1": {
            "id": "valve_1",
            "name": "Test Valve 1",
            "entity_id": "switch.test_valve_1",
            "water_supply_id": "ws_a",
            "zone_id": "zone_1",
        },
        "valve_2": {
            "id": "valve_2",
            "name": "Test Valve 2",
            "entity_id": "switch.test_valve_2",
            "water_supply_id": "ws_b",
            "zone_id": "zone_1",
        },
    }


@pytest.fixture
def sample_water_supplies():
    """Return water supply data as stored in .storage."""
    return [
        {"id": "ws_a", "name": "Arrivee A"},
        {"id": "ws_b", "name": "Arrivee B"},
    ]


@pytest.fixture
def sample_zones():
    """Return zone data as stored in .storage."""
    return [
        {
            "id": "zone_1",
            "name": "Test Zone",
        },
    ]


@pytest.fixture
def sample_programs():
    """Return program data as stored in .storage."""
    return [
        {
            "id": "prog_a",
            "name": "Program A",
            "enabled": True,
            "skip_until": None,
            "schedule": {"times": ["22:00"]},
            "zones": [
                {
                    "zone_id": "zone_1",
                    "valves": [
                        {"valve_id": "valve_1", "duration": 10},
                        {"valve_id": "valve_2", "duration": 15},
                    ],
                }
            ],
        },
        {
            "id": "prog_b",
            "name": "Program B",
            "enabled": False,
            "skip_until": None,
            "schedule": {"times": ["08:00"]},
            "zones": [
                {
                    "zone_id": "zone_1",
                    "valves": [
                        {"valve_id": "valve_1", "duration": 5},
                        {"valve_id": "valve_2", "duration": 5},
                    ],
                }
            ],
        },
    ]
