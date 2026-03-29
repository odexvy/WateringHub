# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""WateringHub coordinator — central logic for scheduling, execution, and mutex."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import EVENT_TYPE, VALVE_PAUSE_SECONDS

_LOGGER = logging.getLogger(__name__)

MAX_SCHEDULE_LOOKAHEAD_DAYS = 400

DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


class WateringHubCoordinator:
    """Central coordinator for WateringHub."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        self.hass = hass
        self._valves: dict[str, dict] = {v["id"]: v for v in config["valves"]}
        self._zones: dict[str, dict] = {z["id"]: z for z in config["zones"]}
        self._programs: dict[str, dict] = {p["id"]: dict(p) for p in config["programs"]}

        self._running_program: str | None = None
        self._cancel_event: asyncio.Event = asyncio.Event()
        self._run_lock: asyncio.Lock = asyncio.Lock()
        self._unsub_time: list = []
        self._listeners: list = []

        self._status: str = "idle"
        self._last_run = None
        self._next_run = None

        # Execution progress tracking
        self._current_program: str | None = None
        self._current_zone: str | None = None
        self._current_zone_name: str | None = None
        self._current_valve: str | None = None
        self._current_valve_name: str | None = None
        self._current_valve_start = None
        self._current_valve_duration: int = 0
        self._valves_done: int = 0
        self._valves_total: int = 0

    # --- State accessors ---

    @property
    def programs(self) -> dict[str, dict]:
        return self._programs

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_run(self):
        return self._last_run

    @property
    def next_run(self):
        return self._next_run

    @property
    def running_program(self) -> str | None:
        return self._running_program

    @property
    def execution_state(self) -> dict:
        """Return current execution details for the status sensor attributes."""
        if self._status != "running":
            return {
                "current_program": None,
                "current_zone": None,
                "current_zone_name": None,
                "current_valve": None,
                "current_valve_name": None,
                "current_valve_start": None,
                "current_valve_duration": None,
                "valves_done": None,
                "valves_total": None,
                "progress_percent": None,
            }

        total_seconds = self._valves_total * 60 if self._valves_total else 1
        done_seconds = self._valves_done * 60
        progress = int((done_seconds / total_seconds) * 100) if total_seconds else 0

        return {
            "current_program": self._current_program,
            "current_zone": self._current_zone,
            "current_zone_name": self._current_zone_name,
            "current_valve": self._current_valve,
            "current_valve_name": self._current_valve_name,
            "current_valve_start": (
                self._current_valve_start.isoformat() if self._current_valve_start else None
            ),
            "current_valve_duration": self._current_valve_duration,
            "valves_done": self._valves_done,
            "valves_total": self._valves_total,
            "progress_percent": progress,
        }

    # --- Listeners ---

    def add_listener(self, callback) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback) -> None:
        self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        for callback in self._listeners:
            self.hass.loop.call_soon_threadsafe(callback)

    # --- Program details (for switch attributes) ---

    def get_program_details(self, program_id: str) -> dict:
        """Resolve a program's zones and valves into full details with names."""
        program = self._programs.get(program_id, {})
        zones = []
        total_duration = 0

        for zone_ref in program.get("zones", []):
            zone = self._zones.get(zone_ref["zone_id"])
            if not zone:
                continue
            valves = []
            for valve_ref in zone_ref.get("valves", []):
                valve = self._valves.get(valve_ref["valve_id"])
                if not valve:
                    continue
                valves.append(
                    {
                        "valve_id": valve_ref["valve_id"],
                        "valve_name": valve["name"],
                        "duration": valve_ref["duration"],
                    }
                )
                total_duration += valve_ref["duration"]
            zones.append(
                {
                    "zone_id": zone_ref["zone_id"],
                    "zone_name": zone["name"],
                    "valves": valves,
                }
            )

        return {
            "program_id": program_id,
            "schedule": program.get("schedule", {}),
            "zones": zones,
            "total_duration": total_duration,
        }

    # --- Mutex ---

    async def async_enable_program(self, program_id: str) -> None:
        """Enable a program, disabling all others (mutex)."""
        if self._running_program and self._running_program != program_id:
            await self.async_stop_all()

        for pid in self._programs:
            self._programs[pid]["enabled"] = pid == program_id

        self._recalculate_next_run()
        self._notify_listeners()
        _LOGGER.info("Program '%s' enabled", program_id)

    async def async_disable_program(self, program_id: str) -> None:
        """Disable a specific program."""
        self._programs[program_id]["enabled"] = False

        if self._running_program == program_id:
            await self.async_stop_all()

        self._recalculate_next_run()
        self._notify_listeners()
        _LOGGER.info("Program '%s' disabled", program_id)

    async def async_stop_all(self) -> None:
        """Stop any running program and close all valves."""
        self._cancel_event.set()
        self._running_program = None

        # Only reset to idle if not in error state
        if self._status != "error":
            self._status = "idle"

        for valve in self._valves.values():
            try:
                await self.hass.services.async_call(
                    "switch",
                    "turn_off",
                    {"entity_id": valve["entity_id"]},
                    blocking=True,
                )
            except Exception:
                _LOGGER.exception("Failed to close valve '%s'", valve["id"])

        self._notify_listeners()
        _LOGGER.info("All valves closed, execution stopped")

    # --- Scheduling ---

    def start(self) -> None:
        """Start the scheduler. Called once from async_setup."""
        self._cancel_event.clear()
        self._recalculate_next_run()

        unsub = async_track_time_change(
            self.hass,
            self._async_time_tick,
            second=0,
        )
        self._unsub_time.append(unsub)
        _LOGGER.info("WateringHub scheduler started")

    async def async_stop(self) -> None:
        """Stop the scheduler and clean up."""
        for unsub in self._unsub_time:
            unsub()
        self._unsub_time.clear()
        await self.async_stop_all()

    async def _async_time_tick(self, now) -> None:
        """Called every minute. Check if a program should run."""
        if self._running_program:
            return

        active = self._get_active_program()
        if not active:
            return

        schedule = active["schedule"]
        target_time = schedule["time"]
        current_time = now.strftime("%H:%M")

        if current_time != target_time:
            return

        if not self._should_run_today(active, now):
            return

        _LOGGER.info("Triggering program '%s'", active["id"])
        await self.async_run_program(active["id"])

    def _get_active_program(self) -> dict | None:
        """Return the single enabled program, or None."""
        for program in self._programs.values():
            if program["enabled"]:
                return program
        return None

    def _should_run_today(self, program: dict, now) -> bool:
        """Check if a program should run today based on schedule type."""
        schedule = program["schedule"]
        schedule_type = schedule["type"]

        if schedule_type == "daily":
            return True

        if schedule_type == "weekdays":
            current_weekday: int = now.weekday()
            allowed_days = schedule.get("days", [])
            return bool(current_weekday in [DAY_MAP[d] for d in allowed_days if d in DAY_MAP])

        if schedule_type == "every_n_days":
            n = schedule.get("n", 1)
            start_str = schedule.get("start_date")
            if not start_str:
                return True
            start_date = date.fromisoformat(start_str)
            today = now.date() if hasattr(now, "date") else now
            delta: int = (today - start_date).days
            return bool(delta >= 0 and delta % n == 0)

        return False

    def _recalculate_next_run(self) -> None:
        """Recalculate the next_run datetime based on the active program."""
        active = self._get_active_program()
        if not active:
            self._next_run = None
            return

        schedule = active["schedule"]
        hour, minute = map(int, schedule["time"].split(":"))
        now = dt_util.now()
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if candidate <= now:
            candidate += timedelta(days=1)

        for _ in range(MAX_SCHEDULE_LOOKAHEAD_DAYS):
            if self._should_run_today(active, candidate):
                self._next_run = candidate
                return
            candidate += timedelta(days=1)

        self._next_run = None

    # --- Executor ---

    async def async_run_program(self, program_id: str) -> None:
        """Execute a program: run each zone's valves sequentially."""
        if self._run_lock.locked():
            _LOGGER.warning("Program execution already in progress, skipping")
            return

        async with self._run_lock:
            program = self._programs.get(program_id)
            if not program:
                _LOGGER.error("Program '%s' not found", program_id)
                return

            self._cancel_event.clear()
            self._running_program = program_id
            self._current_program = program_id
            self._status = "running"
            self._valves_done = 0
            self._valves_total = sum(
                len(zone_ref.get("valves", [])) for zone_ref in program["zones"]
            )
            self._notify_listeners()

            self.hass.bus.async_fire(
                EVENT_TYPE,
                {"action": "program_started", "program": program_id},
            )

            try:
                for zone_ref in program["zones"]:
                    zone = self._zones.get(zone_ref["zone_id"])
                    if not zone:
                        _LOGGER.warning("Zone '%s' not found, skipping", zone_ref["zone_id"])
                        continue

                    self._current_zone = zone_ref["zone_id"]
                    self._current_zone_name = zone["name"]

                    for valve_ref in zone_ref.get("valves", []):
                        if self._cancel_event.is_set():
                            _LOGGER.info("Execution cancelled")
                            return

                        valve = self._valves.get(valve_ref["valve_id"])
                        if not valve:
                            _LOGGER.warning(
                                "Valve '%s' not found, skipping",
                                valve_ref["valve_id"],
                            )
                            continue

                        await self._async_run_valve(valve, valve_ref["duration"])
                        self._valves_done += 1
                        self._notify_listeners()

                self._status = "idle"
                self._last_run = dt_util.now()
                self._recalculate_next_run()

                self.hass.bus.async_fire(
                    EVENT_TYPE,
                    {"action": "program_finished", "program": program_id},
                )

            except Exception as err:
                _LOGGER.exception("Error running program '%s'", program_id)
                self._status = "error"
                await self.async_stop_all()

                self.hass.bus.async_fire(
                    EVENT_TYPE,
                    {
                        "action": "program_error",
                        "program": program_id,
                        "error": str(err),
                    },
                )

            finally:
                self._running_program = None
                self._current_program = None
                self._current_zone = None
                self._current_zone_name = None
                self._current_valve = None
                self._current_valve_name = None
                self._current_valve_start = None
                self._current_valve_duration = 0
                self._valves_done = 0
                self._valves_total = 0
                self._notify_listeners()

    async def _async_run_valve(self, valve: dict, duration_minutes: int) -> None:
        """Open a valve, wait for duration, close it."""
        entity_id = valve["entity_id"]
        valve_id = valve["id"]
        duration_seconds = duration_minutes * 60

        self._current_valve = valve_id
        self._current_valve_name = valve["name"]
        self._current_valve_duration = duration_seconds
        self._current_valve_start = dt_util.now()
        self._notify_listeners()

        _LOGGER.info("Opening valve '%s' for %d min", valve_id, duration_minutes)

        self.hass.bus.async_fire(
            EVENT_TYPE,
            {
                "action": "valve_opened",
                "valve": valve_id,
                "duration": duration_seconds,
            },
        )

        await self.hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": entity_id},
            blocking=True,
        )

        # Wait for duration, checking cancel every second
        for _ in range(duration_seconds):
            if self._cancel_event.is_set():
                break
            await asyncio.sleep(1)

        await self.hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

        self.hass.bus.async_fire(
            EVENT_TYPE,
            {"action": "valve_closed", "valve": valve_id},
        )

        _LOGGER.info("Valve '%s' closed", valve_id)

        # Pause between valves
        if not self._cancel_event.is_set():
            await asyncio.sleep(VALVE_PAUSE_SECONDS)
