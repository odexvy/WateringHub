# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""Tests for config validation — now only validates valves from YAML."""

from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.wateringhub.__init__ import CONFIG_SCHEMA


class TestConfigSchema:
    """Test YAML config validation (valves only)."""

    def test_valid_config(self):
        config = {
            "wateringhub": {
                "valves": [
                    {"id": "v1", "name": "Valve 1", "entity_id": "switch.v1"},
                ]
            }
        }
        result = CONFIG_SCHEMA(config)
        assert len(result["wateringhub"]["valves"]) == 1

    def test_valve_requires_id(self):
        config = {"wateringhub": {"valves": [{"name": "Valve 1", "entity_id": "switch.v1"}]}}
        with pytest.raises(vol.Invalid):
            CONFIG_SCHEMA(config)

    def test_valve_requires_entity_id(self):
        config = {"wateringhub": {"valves": [{"id": "v1", "name": "Valve 1"}]}}
        with pytest.raises(vol.Invalid):
            CONFIG_SCHEMA(config)

    def test_valves_required(self):
        config = {"wateringhub": {}}
        with pytest.raises(vol.Invalid):
            CONFIG_SCHEMA(config)

    def test_optional_flow_sensor(self):
        config = {
            "wateringhub": {
                "valves": [
                    {
                        "id": "v1",
                        "name": "Valve 1",
                        "entity_id": "switch.v1",
                        "flow_sensor": "sensor.flow_v1",
                    }
                ]
            }
        }
        result = CONFIG_SCHEMA(config)
        assert result["wateringhub"]["valves"][0]["flow_sensor"] == "sensor.flow_v1"
