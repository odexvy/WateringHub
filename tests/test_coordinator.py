# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""Tests for WateringHubCoordinator."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.wateringhub.coordinator import (
    DAY_MAP,
    WateringHubCoordinator,
)


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.bus = MagicMock()
    hass.loop = MagicMock()
    return hass


@pytest.fixture
def coordinator(mock_hass, sample_config):
    """Create a coordinator with sample config."""
    return WateringHubCoordinator(mock_hass, sample_config)


class TestInit:
    """Test coordinator initialization."""

    def test_parses_valves(self, coordinator):
        assert "valve_1" in coordinator._valves
        assert "valve_2" in coordinator._valves
        assert coordinator._valves["valve_1"]["name"] == "Test Valve 1"

    def test_parses_zones(self, coordinator):
        assert "zone_1" in coordinator._zones
        assert len(coordinator._zones["zone_1"]["valves"]) == 2

    def test_parses_programs(self, coordinator):
        assert "prog_a" in coordinator.programs
        assert "prog_b" in coordinator.programs
        assert coordinator.programs["prog_a"]["enabled"] is True
        assert coordinator.programs["prog_b"]["enabled"] is False

    def test_initial_status(self, coordinator):
        assert coordinator.status == "idle"
        assert coordinator.running_program is None
        assert coordinator.last_run is None


class TestMutex:
    """Test program enable/disable mutex."""

    @pytest.mark.asyncio
    async def test_enable_disables_others(self, coordinator):
        await coordinator.async_enable_program("prog_b")
        assert coordinator.programs["prog_b"]["enabled"] is True
        assert coordinator.programs["prog_a"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_enable_already_enabled(self, coordinator):
        await coordinator.async_enable_program("prog_a")
        assert coordinator.programs["prog_a"]["enabled"] is True
        assert coordinator.programs["prog_b"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_disable_program(self, coordinator):
        await coordinator.async_disable_program("prog_a")
        assert coordinator.programs["prog_a"]["enabled"] is False

    @pytest.mark.asyncio
    async def test_enable_stops_running_program(self, coordinator, mock_hass):
        coordinator._running_program = "prog_a"
        await coordinator.async_enable_program("prog_b")
        # stop_all should have been triggered (closes valves)
        assert mock_hass.services.async_call.called
        assert coordinator.programs["prog_b"]["enabled"] is True


class TestScheduling:
    """Test schedule evaluation."""

    def test_should_run_daily(self, coordinator):
        now = datetime(2026, 3, 29, 22, 0)
        program = coordinator.programs["prog_a"]
        assert coordinator._should_run_today(program, now) is True

    def test_should_run_every_n_days_match(self, coordinator):
        # start_date is 2026-01-01, n=2. Day 0 (Jan 1) runs, day 2 (Jan 3) runs.
        now = datetime(2026, 1, 3, 8, 0)
        program = coordinator.programs["prog_b"]
        assert coordinator._should_run_today(program, now) is True

    def test_should_run_every_n_days_no_match(self, coordinator):
        # Day 1 (Jan 2) should NOT run
        now = datetime(2026, 1, 2, 8, 0)
        program = coordinator.programs["prog_b"]
        assert coordinator._should_run_today(program, now) is False

    def test_should_run_weekdays(self, coordinator):
        # Create a weekdays program
        program = {
            "schedule": {"type": "weekdays", "days": ["mon", "fri"]},
        }
        # 2026-03-30 is a Monday
        now = datetime(2026, 3, 30, 22, 0)
        assert coordinator._should_run_today(program, now) is True

        # 2026-03-31 is a Tuesday
        now = datetime(2026, 3, 31, 22, 0)
        assert coordinator._should_run_today(program, now) is False

    def test_day_map_completeness(self):
        assert len(DAY_MAP) == 7
        assert DAY_MAP["mon"] == 0
        assert DAY_MAP["sun"] == 6


class TestNextRun:
    """Test next_run calculation."""

    @patch("custom_components.wateringhub.coordinator.dt_util")
    def test_next_run_daily(self, mock_dt, coordinator):
        mock_dt.now.return_value = datetime(2026, 3, 29, 20, 0, tzinfo=None)
        coordinator._recalculate_next_run()
        assert coordinator.next_run is not None
        assert coordinator.next_run.hour == 22
        assert coordinator.next_run.minute == 0

    @patch("custom_components.wateringhub.coordinator.dt_util")
    def test_next_run_past_today(self, mock_dt, coordinator):
        # If it's already 23:00, next run is tomorrow
        mock_dt.now.return_value = datetime(2026, 3, 29, 23, 0, tzinfo=None)
        coordinator._recalculate_next_run()
        assert coordinator.next_run is not None
        assert coordinator.next_run.day == 30

    def test_next_run_no_active_program(self, coordinator):
        coordinator._programs["prog_a"]["enabled"] = False
        coordinator._recalculate_next_run()
        assert coordinator.next_run is None


class TestStopAll:
    """Test stop_all behavior."""

    @pytest.mark.asyncio
    async def test_closes_all_valves(self, coordinator, mock_hass):
        await coordinator.async_stop_all()
        assert mock_hass.services.async_call.call_count == 2
        calls = mock_hass.services.async_call.call_args_list
        entity_ids = [c[0][2]["entity_id"] for c in calls]
        assert "switch.test_valve_1" in entity_ids
        assert "switch.test_valve_2" in entity_ids

    @pytest.mark.asyncio
    async def test_preserves_error_status(self, coordinator):
        coordinator._status = "error"
        await coordinator.async_stop_all()
        assert coordinator.status == "error"

    @pytest.mark.asyncio
    async def test_resets_idle_status(self, coordinator):
        coordinator._status = "running"
        await coordinator.async_stop_all()
        assert coordinator.status == "idle"


class TestProgramDetails:
    """Test get_program_details."""

    def test_resolves_zones_and_valves(self, coordinator):
        details = coordinator.get_program_details("prog_a")
        assert details["program_id"] == "prog_a"
        assert details["total_duration"] == 25
        assert len(details["zones"]) == 1
        assert details["zones"][0]["zone_name"] == "Test Zone"
        assert len(details["zones"][0]["valves"]) == 2

    def test_unknown_program(self, coordinator):
        details = coordinator.get_program_details("nonexistent")
        assert details["total_duration"] == 0
        assert details["zones"] == []
