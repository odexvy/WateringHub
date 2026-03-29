# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""Tests for config validation."""
from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.wateringhub.__init__ import (
    _validate_cross_references,
    _validate_date,
    _validate_time,
)


class TestValidateTime:
    """Test time format validation."""

    def test_valid_time(self):
        assert _validate_time("22:00") == "22:00"
        assert _validate_time("00:00") == "00:00"
        assert _validate_time("23:59") == "23:59"

    def test_invalid_format(self):
        with pytest.raises(vol.Invalid):
            _validate_time("25:00")

    def test_invalid_string(self):
        with pytest.raises(vol.Invalid):
            _validate_time("hello")

    def test_invalid_minutes(self):
        with pytest.raises(vol.Invalid):
            _validate_time("22:60")


class TestValidateDate:
    """Test date format validation."""

    def test_valid_date(self):
        assert _validate_date("2026-03-28") == "2026-03-28"

    def test_invalid_format(self):
        with pytest.raises(vol.Invalid):
            _validate_date("28/03/2026")

    def test_invalid_date(self):
        with pytest.raises(vol.Invalid):
            _validate_date("2026-13-01")


class TestCrossReferences:
    """Test cross-reference validation."""

    def test_valid_references(self, sample_config):
        _validate_cross_references(sample_config)

    def test_zone_references_unknown_valve(self, sample_config):
        sample_config["zones"][0]["valves"][0]["valve_id"] = "nonexistent"
        with pytest.raises(vol.Invalid, match="unknown valve"):
            _validate_cross_references(sample_config)

    def test_program_references_unknown_zone(self, sample_config):
        sample_config["programs"][0]["zones"][0]["zone_id"] = "nonexistent"
        with pytest.raises(vol.Invalid, match="unknown zone"):
            _validate_cross_references(sample_config)
