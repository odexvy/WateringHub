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
def coordinator(mock_hass, sample_valves, sample_zones, sample_programs):
    """Create a coordinator with sample data."""
    coord = WateringHubCoordinator(mock_hass)
    coord._valves = sample_valves
    # Manually load zones and programs (bypassing storage)
    coord._zones = {z["id"]: z for z in sample_zones}
    coord._programs = {p["id"]: dict(p) for p in sample_programs}
    coord._active_program = "prog_a"
    # Mock storage
    coord._store = MagicMock()
    coord._store.async_save = AsyncMock()
    return coord


class TestInit:
    """Test coordinator initialization."""

    def test_parses_valves(self, coordinator):
        assert "valve_1" in coordinator.valves
        assert "valve_2" in coordinator.valves
        assert coordinator.valves["valve_1"]["name"] == "Test Valve 1"

    def test_has_zones(self, coordinator):
        assert "zone_1" in coordinator.zones
        assert len(coordinator.zones["zone_1"]["valves"]) == 2

    def test_has_programs(self, coordinator):
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
        assert mock_hass.services.async_call.called
        assert coordinator.programs["prog_b"]["enabled"] is True

    @pytest.mark.asyncio
    async def test_enable_persists(self, coordinator):
        await coordinator.async_enable_program("prog_b")
        coordinator._store.async_save.assert_called()


class TestFrequency:
    """Test per-valve frequency evaluation."""

    def test_no_frequency_always_runs(self):
        now = datetime(2026, 3, 29, 22, 0)
        assert WateringHubCoordinator._check_frequency({}, now) is True

    def test_every_n_days_match(self):
        freq = {"type": "every_n_days", "n": 2, "start_date": "2026-01-01"}
        now = datetime(2026, 1, 3, 8, 0)  # day 2 from start, 2%2=0
        assert WateringHubCoordinator._check_frequency(freq, now) is True

    def test_every_n_days_no_match(self):
        freq = {"type": "every_n_days", "n": 2, "start_date": "2026-01-01"}
        now = datetime(2026, 1, 2, 8, 0)  # day 1 from start, 1%2=1
        assert WateringHubCoordinator._check_frequency(freq, now) is False

    def test_weekdays_match(self):
        freq = {"type": "weekdays", "days": ["mon", "fri"]}
        now = datetime(2026, 3, 30, 22, 0)  # Monday
        assert WateringHubCoordinator._check_frequency(freq, now) is True

    def test_weekdays_no_match(self):
        freq = {"type": "weekdays", "days": ["mon", "fri"]}
        now = datetime(2026, 3, 31, 22, 0)  # Tuesday
        assert WateringHubCoordinator._check_frequency(freq, now) is False

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


class TestCRUDZones:
    """Test zone CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_zone(self, coordinator):
        await coordinator.async_create_zone("zone_2", "New Zone", ["valve_1"])
        assert "zone_2" in coordinator.zones
        assert coordinator.zones["zone_2"]["name"] == "New Zone"

    @pytest.mark.asyncio
    async def test_create_zone_duplicate(self, coordinator):
        with pytest.raises(ValueError, match="already exists"):
            await coordinator.async_create_zone("zone_1", "Dup", ["valve_1"])

    @pytest.mark.asyncio
    async def test_create_zone_unknown_valve(self, coordinator):
        with pytest.raises(ValueError, match="Unknown valve"):
            await coordinator.async_create_zone("zone_2", "Bad", ["nonexistent"])

    @pytest.mark.asyncio
    async def test_update_zone(self, coordinator):
        await coordinator.async_update_zone("zone_1", name="Renamed")
        assert coordinator.zones["zone_1"]["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_delete_zone_in_use(self, coordinator):
        with pytest.raises(ValueError, match="used by program"):
            await coordinator.async_delete_zone("zone_1")

    @pytest.mark.asyncio
    async def test_delete_zone(self, coordinator):
        await coordinator.async_create_zone("zone_unused", "Unused", ["valve_1"])
        await coordinator.async_delete_zone("zone_unused")
        assert "zone_unused" not in coordinator.zones


class TestCRUDPrograms:
    """Test program CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_program(self, coordinator):
        coordinator._add_entities_callback = MagicMock()
        await coordinator.async_create_program(
            "prog_c",
            "Program C",
            {"type": "daily", "time": "06:00"},
            [{"zone_id": "zone_1", "valves": [{"valve_id": "valve_1", "duration": 5}]}],
        )
        assert "prog_c" in coordinator.programs
        coordinator._add_entities_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_program_duplicate(self, coordinator):
        with pytest.raises(ValueError, match="already exists"):
            await coordinator.async_create_program(
                "prog_a", "Dup", {"type": "daily", "time": "06:00"}, []
            )

    @pytest.mark.asyncio
    async def test_update_program(self, coordinator):
        await coordinator.async_update_program("prog_a", name="Renamed")
        assert coordinator.programs["prog_a"]["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_delete_program(self, coordinator):
        coordinator._remove_entity_callback = MagicMock()
        await coordinator.async_delete_program("prog_b")
        assert "prog_b" not in coordinator.programs
        coordinator._remove_entity_callback.assert_called_once_with("prog_b")


class TestSkipProgram:
    """Test skip_program functionality."""

    @pytest.mark.asyncio
    async def test_skip_sets_field(self, coordinator):
        """days > 0 sets skip_until to today + days as ISO string."""
        with patch("custom_components.wateringhub.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 10, 12, 0)
            await coordinator.async_skip_program("prog_a", 3)
        assert coordinator.programs["prog_a"]["skip_until"] == "2026-04-13"

    @pytest.mark.asyncio
    async def test_skip_zero_clears(self, coordinator):
        """days = 0 clears skip_until to None."""
        coordinator._programs["prog_a"]["skip_until"] = "2026-12-31"
        await coordinator.async_skip_program("prog_a", 0)
        assert coordinator.programs["prog_a"]["skip_until"] is None

    @pytest.mark.asyncio
    async def test_skip_nonexistent_raises(self, coordinator):
        """Raises ValueError for unknown program_id."""
        with pytest.raises(ValueError, match="not found"):
            await coordinator.async_skip_program("nonexistent", 3)

    @pytest.mark.asyncio
    async def test_skip_disabled_raises(self, coordinator):
        """Raises ValueError for disabled program."""
        with pytest.raises(ValueError, match="not enabled"):
            await coordinator.async_skip_program("prog_b", 3)

    @pytest.mark.asyncio
    async def test_skip_persists(self, coordinator):
        """Skip triggers storage save."""
        with patch("custom_components.wateringhub.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 10, 12, 0)
            await coordinator.async_skip_program("prog_a", 2)
        coordinator._store.async_save.assert_called()

    def test_next_run_reflects_skip(self, coordinator):
        """next_run jumps to skip_until date when skip is active."""
        with patch("custom_components.wateringhub.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 10, 20, 0)
            coordinator._programs["prog_a"]["skip_until"] = "2026-04-15"
            coordinator._recalculate_next_run()
        assert coordinator.next_run is not None
        assert coordinator.next_run.month == 4
        assert coordinator.next_run.day == 15
        assert coordinator.next_run.hour == 22

    def test_next_run_no_skip(self, coordinator):
        """next_run is normal when skip_until is None."""
        with patch("custom_components.wateringhub.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 10, 20, 0)
            coordinator._programs["prog_a"]["skip_until"] = None
            coordinator._recalculate_next_run()
        # 20:00 < 22:00, so next_run is today at 22:00
        assert coordinator.next_run.day == 10
        assert coordinator.next_run.hour == 22

    @pytest.mark.asyncio
    async def test_auto_clear_on_expiry(self, coordinator):
        """_async_time_tick auto-clears skip_until when expired."""
        # Set skip_until to today (should expire and clear)
        coordinator._programs["prog_a"]["skip_until"] = "2026-04-10"
        now = datetime(2026, 4, 10, 22, 0)
        with patch("custom_components.wateringhub.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = now
            await coordinator._async_time_tick(now)
        assert coordinator.programs["prog_a"]["skip_until"] is None
