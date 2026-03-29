# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""Shared test fixtures for WateringHub."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_valves():
    """Return valve config as parsed from YAML."""
    return {
        "valve_1": {
            "id": "valve_1",
            "name": "Test Valve 1",
            "entity_id": "switch.test_valve_1",
        },
        "valve_2": {
            "id": "valve_2",
            "name": "Test Valve 2",
            "entity_id": "switch.test_valve_2",
        },
    }


@pytest.fixture
def sample_zones():
    """Return zone data as stored in .storage."""
    return [
        {
            "id": "zone_1",
            "name": "Test Zone",
            "valves": ["valve_1", "valve_2"],
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
            "schedule": {"type": "daily", "time": "22:00"},
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
            "schedule": {
                "type": "every_n_days",
                "n": 2,
                "start_date": "2026-01-01",
                "time": "08:00",
            },
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
