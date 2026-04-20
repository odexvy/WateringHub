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
def coordinator(mock_hass, sample_valves, sample_zones, sample_programs, sample_water_supplies):
    """Create a coordinator with sample data."""
    coord = WateringHubCoordinator(mock_hass)
    coord._valves = sample_valves
    coord._water_supplies = {ws["id"]: ws for ws in sample_water_supplies}
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
        assert coordinator.zones["zone_1"]["name"] == "Test Zone"

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

    @patch("custom_components.wateringhub.coordinator.dt_util")
    def test_next_run_multiple_times_picks_earliest_future(self, mock_dt, coordinator):
        """With times ['06:00', '22:00'] at 20:00, next_run = today 22:00."""
        coordinator._programs["prog_a"]["schedule"] = {"times": ["06:00", "22:00"]}
        mock_dt.now.return_value = datetime(2026, 3, 29, 20, 0, tzinfo=None)
        coordinator._recalculate_next_run()
        assert coordinator.next_run is not None
        assert coordinator.next_run.hour == 22
        assert coordinator.next_run.day == 29

    @patch("custom_components.wateringhub.coordinator.dt_util")
    def test_next_run_multiple_times_wraps_to_tomorrow(self, mock_dt, coordinator):
        """With times ['06:00', '22:00'] at 23:00, next_run = tomorrow 06:00."""
        coordinator._programs["prog_a"]["schedule"] = {"times": ["06:00", "22:00"]}
        mock_dt.now.return_value = datetime(2026, 3, 29, 23, 0, tzinfo=None)
        coordinator._recalculate_next_run()
        assert coordinator.next_run is not None
        assert coordinator.next_run.hour == 6
        assert coordinator.next_run.day == 30

    @patch("custom_components.wateringhub.coordinator.dt_util")
    def test_next_run_empty_times(self, mock_dt, coordinator):
        """Empty times list → next_run is None."""
        coordinator._programs["prog_a"]["schedule"] = {"times": []}
        mock_dt.now.return_value = datetime(2026, 3, 29, 20, 0, tzinfo=None)
        coordinator._recalculate_next_run()
        assert coordinator.next_run is None


class TestScheduleTrigger:
    """Test _async_time_tick fires at each scheduled time."""

    @pytest.mark.asyncio
    async def test_fires_at_first_time(self, coordinator):
        """Program with times ['06:00', '22:00'] fires at 06:00."""
        coordinator._programs["prog_a"]["schedule"] = {"times": ["06:00", "22:00"]}
        coordinator.async_run_program = AsyncMock()
        with patch("custom_components.wateringhub.coordinator.dt_util") as mock_dt:
            now = datetime(2026, 3, 29, 6, 0, tzinfo=None)
            mock_dt.now.return_value = now
            await coordinator._async_time_tick(now)
        coordinator.async_run_program.assert_called_once_with("prog_a")

    @pytest.mark.asyncio
    async def test_fires_at_second_time(self, coordinator):
        """Program with times ['06:00', '22:00'] fires at 22:00."""
        coordinator._programs["prog_a"]["schedule"] = {"times": ["06:00", "22:00"]}
        coordinator.async_run_program = AsyncMock()
        with patch("custom_components.wateringhub.coordinator.dt_util") as mock_dt:
            now = datetime(2026, 3, 29, 22, 0, tzinfo=None)
            mock_dt.now.return_value = now
            await coordinator._async_time_tick(now)
        coordinator.async_run_program.assert_called_once_with("prog_a")

    @pytest.mark.asyncio
    async def test_does_not_fire_between_times(self, coordinator):
        """Program with times ['06:00', '22:00'] does not fire at 12:00."""
        coordinator._programs["prog_a"]["schedule"] = {"times": ["06:00", "22:00"]}
        coordinator.async_run_program = AsyncMock()
        with patch("custom_components.wateringhub.coordinator.dt_util") as mock_dt:
            now = datetime(2026, 3, 29, 12, 0, tzinfo=None)
            mock_dt.now.return_value = now
            await coordinator._async_time_tick(now)
        coordinator.async_run_program.assert_not_called()

    @pytest.mark.asyncio
    async def test_trigger_time_passed_to_run_program(self, coordinator):
        """_async_time_tick passes current_time to async_run_program."""
        coordinator._programs["prog_a"]["schedule"] = {"times": ["06:00", "22:00"]}
        coordinator.async_run_program = AsyncMock()
        with patch("custom_components.wateringhub.coordinator.dt_util") as mock_dt:
            now = datetime(2026, 3, 29, 6, 0, tzinfo=None)
            mock_dt.now.return_value = now
            await coordinator._async_time_tick(now)
        coordinator.async_run_program.assert_called_once_with("prog_a", trigger_time="06:00")


class TestPerValveTimes:
    """Test per-valve times filtering in _build_valves_sequence."""

    def test_valve_without_times_runs_at_all_times(self, coordinator):
        """A valve without `times` override runs at every trigger_time."""
        program = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "valves": [{"valve_id": "valve_1", "duration": 5}],
                }
            ]
        }
        now = datetime(2026, 3, 29, 22, 0)
        seq = coordinator._build_valves_sequence(program, now, trigger_time="06:00")
        assert len(seq) == 1
        assert seq[0]["valve_id"] == "valve_1"

    def test_valve_with_times_filtered_out(self, coordinator):
        """A valve with `times: ['22:00']` is skipped at trigger_time='06:00'."""
        program = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "valves": [
                        {"valve_id": "valve_1", "duration": 5, "times": ["22:00"]},
                    ],
                }
            ]
        }
        now = datetime(2026, 3, 29, 6, 0)
        seq = coordinator._build_valves_sequence(program, now, trigger_time="06:00")
        assert seq == []

    def test_valve_with_times_included(self, coordinator):
        """A valve with `times: ['22:00']` runs at trigger_time='22:00'."""
        program = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "valves": [
                        {"valve_id": "valve_1", "duration": 5, "times": ["22:00"]},
                    ],
                }
            ]
        }
        now = datetime(2026, 3, 29, 22, 0)
        seq = coordinator._build_valves_sequence(program, now, trigger_time="22:00")
        assert len(seq) == 1

    def test_mixed_valves_per_time(self, coordinator):
        """Program at 06:00: only valves with no times OR times containing '06:00' run."""
        program = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "valves": [
                        {"valve_id": "valve_1", "duration": 5},  # always
                        {
                            "valve_id": "valve_2",
                            "duration": 5,
                            "times": ["06:00", "22:00"],
                        },
                    ],
                }
            ]
        }
        now = datetime(2026, 3, 29, 6, 0)
        seq = coordinator._build_valves_sequence(program, now, trigger_time="06:00")
        assert len(seq) == 2

        seq_22 = coordinator._build_valves_sequence(program, now, trigger_time="22:00")
        assert len(seq_22) == 2

    def test_trigger_time_none_bypasses_valve_times(self, coordinator):
        """If trigger_time is None (manual call), valve times filter is bypassed."""
        program = {
            "zones": [
                {
                    "zone_id": "zone_1",
                    "valves": [
                        {"valve_id": "valve_1", "duration": 5, "times": ["22:00"]},
                    ],
                }
            ]
        }
        now = datetime(2026, 3, 29, 12, 0)
        seq = coordinator._build_valves_sequence(program, now, trigger_time=None)
        assert len(seq) == 1  # not filtered out when trigger_time is None


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
        # max(ws_a=10, ws_b=15) = 15
        assert details["total_duration"] == 15
        assert len(details["zones"]) == 1
        assert details["zones"][0]["zone_name"] == "Test Zone"
        assert len(details["zones"][0]["valves"]) == 2

    def test_unknown_program(self, coordinator):
        details = coordinator.get_program_details("nonexistent")
        assert details["total_duration"] == 0
        assert details["zones"] == []

    def test_valve_times_echoed_when_set(self, coordinator):
        """valve_ref.times is echoed sorted in get_program_details output."""
        coordinator._programs["prog_a"]["zones"][0]["valves"][0]["times"] = [
            "22:00",
            "06:00",
        ]
        details = coordinator.get_program_details("prog_a")
        valves = details["zones"][0]["valves"]
        assert valves[0]["times"] == ["06:00", "22:00"]
        # Other valve without times override → no times key
        assert "times" not in valves[1]

    def test_valve_times_omitted_when_absent(self, coordinator):
        """Valves without times override have no times key in output."""
        details = coordinator.get_program_details("prog_a")
        for valve in details["zones"][0]["valves"]:
            assert "times" not in valve


class TestCRUDZones:
    """Test zone CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_zone(self, coordinator):
        await coordinator.async_create_zone("zone_2", "New Zone")
        assert "zone_2" in coordinator.zones
        assert coordinator.zones["zone_2"]["name"] == "New Zone"
        assert "valves" not in coordinator.zones["zone_2"]

    @pytest.mark.asyncio
    async def test_create_zone_duplicate(self, coordinator):
        with pytest.raises(ValueError, match="already exists"):
            await coordinator.async_create_zone("zone_1", "Dup")

    @pytest.mark.asyncio
    async def test_update_zone(self, coordinator):
        await coordinator.async_update_zone("zone_1", name="Renamed")
        assert coordinator.zones["zone_1"]["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_update_zone_not_found(self, coordinator):
        with pytest.raises(ValueError, match="not found"):
            await coordinator.async_update_zone("nonexistent", name="X")

    @pytest.mark.asyncio
    async def test_delete_zone(self, coordinator):
        await coordinator.async_create_zone("zone_unused", "Unused")
        await coordinator.async_delete_zone("zone_unused")
        assert "zone_unused" not in coordinator.zones

    @pytest.mark.asyncio
    async def test_delete_zone_clears_valve_zone_id(self, coordinator):
        """Deleting a zone sets zone_id to null on valves that referenced it."""
        await coordinator.async_delete_zone("zone_1")
        assert "zone_1" not in coordinator.zones
        assert coordinator.valves["valve_1"]["zone_id"] is None
        assert coordinator.valves["valve_2"]["zone_id"] is None

    @pytest.mark.asyncio
    async def test_delete_zone_not_found(self, coordinator):
        with pytest.raises(ValueError, match="not found"):
            await coordinator.async_delete_zone("nonexistent")

    @pytest.mark.asyncio
    async def test_create_zone_persists(self, coordinator):
        await coordinator.async_create_zone("zone_2", "New")
        coordinator._store.async_save.assert_called()


class TestCRUDPrograms:
    """Test program CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_program(self, coordinator):
        coordinator._add_entities_callback = MagicMock()
        await coordinator.async_create_program(
            "prog_c",
            "Program C",
            {"times": ["06:00"]},
            [{"zone_id": "zone_1", "valves": [{"valve_id": "valve_1", "duration": 5}]}],
        )
        assert "prog_c" in coordinator.programs
        coordinator._add_entities_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_program_duplicate(self, coordinator):
        with pytest.raises(ValueError, match="already exists"):
            await coordinator.async_create_program("prog_a", "Dup", {"times": ["06:00"]}, [])

    @pytest.mark.asyncio
    async def test_update_program(self, coordinator):
        await coordinator.async_update_program("prog_a", name="Renamed")
        assert coordinator.programs["prog_a"]["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_create_program_valve_not_in_zone(self, coordinator):
        """Valve with different zone_id than referenced zone is rejected."""
        await coordinator.async_create_zone("zone_2", "Empty Zone")
        with pytest.raises(ValueError, match="not in zone"):
            await coordinator.async_create_program(
                "prog_c",
                "Program C",
                {"times": ["06:00"]},
                [{"zone_id": "zone_2", "valves": [{"valve_id": "valve_1", "duration": 5}]}],
            )

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


class TestCRUDWaterSupplies:
    """Test water supply CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_water_supply(self, coordinator):
        await coordinator.async_create_water_supply("ws_new", "New Supply")
        assert "ws_new" in coordinator.water_supplies
        assert coordinator.water_supplies["ws_new"]["name"] == "New Supply"

    @pytest.mark.asyncio
    async def test_create_water_supply_duplicate(self, coordinator):
        with pytest.raises(ValueError, match="already exists"):
            await coordinator.async_create_water_supply("ws_a", "Duplicate")

    @pytest.mark.asyncio
    async def test_update_water_supply(self, coordinator):
        await coordinator.async_update_water_supply("ws_a", name="Renamed")
        assert coordinator.water_supplies["ws_a"]["name"] == "Renamed"

    @pytest.mark.asyncio
    async def test_update_water_supply_not_found(self, coordinator):
        with pytest.raises(ValueError, match="not found"):
            await coordinator.async_update_water_supply("nonexistent", name="X")

    @pytest.mark.asyncio
    async def test_delete_water_supply(self, coordinator):
        await coordinator.async_create_water_supply("ws_unused", "Unused")
        await coordinator.async_delete_water_supply("ws_unused")
        assert "ws_unused" not in coordinator.water_supplies

    @pytest.mark.asyncio
    async def test_delete_water_supply_clears_valve_refs(self, coordinator):
        """Deleting a water supply sets water_supply_id to null on valves that referenced it."""
        await coordinator.async_delete_water_supply("ws_a")
        assert "ws_a" not in coordinator.water_supplies
        assert coordinator.valves["valve_1"]["water_supply_id"] is None

    @pytest.mark.asyncio
    async def test_delete_water_supply_not_found(self, coordinator):
        with pytest.raises(ValueError, match="not found"):
            await coordinator.async_delete_water_supply("nonexistent")

    @pytest.mark.asyncio
    async def test_create_water_supply_persists(self, coordinator):
        await coordinator.async_create_water_supply("ws_new", "New")
        coordinator._store.async_save.assert_called()


class TestSetValves:
    """Test set_valves with zone_id and water_supply_id."""

    @pytest.mark.asyncio
    async def test_set_valves_with_zone_and_supply(self, coordinator):
        await coordinator.async_set_valves(
            [
                {
                    "entity_id": "switch.test_valve_1",
                    "name": "Valve 1",
                    "water_supply_id": "ws_a",
                    "zone_id": "zone_1",
                },
            ]
        )
        valve = next(iter(coordinator.valves.values()))
        assert valve["water_supply_id"] == "ws_a"
        assert valve["zone_id"] == "zone_1"

    @pytest.mark.asyncio
    async def test_set_valves_null_zone_and_supply(self, coordinator):
        await coordinator.async_set_valves(
            [
                {
                    "entity_id": "switch.test_valve_1",
                    "name": "Valve 1",
                    "water_supply_id": None,
                    "zone_id": None,
                },
            ]
        )
        valve = next(iter(coordinator.valves.values()))
        assert valve["water_supply_id"] is None
        assert valve["zone_id"] is None

    @pytest.mark.asyncio
    async def test_set_valves_absent_optional_fields(self, coordinator):
        """Omitted zone_id/water_supply_id default to None."""
        await coordinator.async_set_valves(
            [
                {
                    "entity_id": "switch.test_valve_1",
                    "name": "Valve 1",
                },
            ]
        )
        valve = next(iter(coordinator.valves.values()))
        assert valve["water_supply_id"] is None
        assert valve["zone_id"] is None

    @pytest.mark.asyncio
    async def test_set_valves_invalid_water_supply(self, coordinator):
        with pytest.raises(ValueError, match="Unknown water supply"):
            await coordinator.async_set_valves(
                [
                    {
                        "entity_id": "switch.test_valve_1",
                        "name": "Valve 1",
                        "water_supply_id": "nonexistent",
                    },
                ]
            )

    @pytest.mark.asyncio
    async def test_set_valves_invalid_zone(self, coordinator):
        with pytest.raises(ValueError, match="Unknown zone"):
            await coordinator.async_set_valves(
                [
                    {
                        "entity_id": "switch.test_valve_1",
                        "name": "Valve 1",
                        "zone_id": "nonexistent",
                    },
                ]
            )

    @pytest.mark.asyncio
    async def test_set_valves_persists(self, coordinator):
        await coordinator.async_set_valves(
            [
                {
                    "entity_id": "switch.test_valve_1",
                    "name": "Valve 1",
                    "water_supply_id": "ws_b",
                    "zone_id": "zone_1",
                },
            ]
        )
        coordinator._store.async_save.assert_called()


class TestParallelExecution:
    """Test parallel execution across water supplies."""

    def test_group_by_supply(self):
        """Unit test for _group_by_supply static method."""
        sequence = [
            {"valve_id": "v1", "water_supply_id": "a"},
            {"valve_id": "v2", "water_supply_id": "b"},
            {"valve_id": "v3", "water_supply_id": "a"},
        ]
        groups = WateringHubCoordinator._group_by_supply(sequence)
        assert list(groups.keys()) == ["a", "b"]
        assert len(groups["a"]) == 2
        assert len(groups["b"]) == 1
        assert groups["a"][0]["valve_id"] == "v1"
        assert groups["a"][1]["valve_id"] == "v3"

    def test_total_duration_max_per_supply(self, coordinator):
        """total_duration = max of sum per supply, not raw sum."""
        details = coordinator.get_program_details("prog_a")
        # valve_1 on ws_a: 10 min, valve_2 on ws_b: 15 min
        # max(10, 15) = 15, not 25
        assert details["total_duration"] == 15

    def test_execution_state_has_active_valves(self, coordinator):
        """execution_state returns active_valves, not current_valve_*."""
        state = coordinator.execution_state
        assert "active_valves" in state
        assert "current_valve" not in state
        assert "current_zone" not in state

    def test_build_sequence_has_water_supply_id(self, coordinator):
        """_build_valves_sequence includes water_supply_id and status."""
        program = coordinator.programs["prog_a"]
        with patch("custom_components.wateringhub.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 12, 22, 0)
            sequence = coordinator._build_valves_sequence(program, mock_dt.now())
        assert len(sequence) == 2
        assert sequence[0]["water_supply_id"] == "ws_a"
        assert sequence[1]["water_supply_id"] == "ws_b"
        assert sequence[0]["status"] == "pending"
