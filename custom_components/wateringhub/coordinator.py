# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""WateringHub coordinator — central logic for scheduling, execution, and mutex."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import EVENT_TYPE, STORAGE_KEY, STORAGE_VERSION, VALVE_PAUSE_SECONDS

_LOGGER = logging.getLogger(__name__)

DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


class WateringHubCoordinator:
    """Central coordinator for WateringHub."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._valves: dict[str, dict] = {}
        self._zones: dict[str, dict] = {}
        self._water_supplies: dict[str, dict] = {}
        self._programs: dict[str, dict] = {}
        self._active_program: str | None = None

        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

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
        self._valves_done: int = 0
        self._valves_total: int = 0
        self._valves_sequence: list[dict] = []
        self._active_valves: list[dict] = []
        self._dry_run: bool = False
        self._error_message: str | None = None

        # Callback for dynamic entity management
        self._add_entities_callback = None
        self._remove_entity_callback = None

    # --- Storage ---

    async def async_load(self) -> None:
        """Load valves, zones, programs, and active_program from .storage."""
        data = await self._store.async_load()
        if data:
            self._valves = {v["id"]: v for v in data.get("valves", [])}
            self._zones = {z["id"]: z for z in data.get("zones", [])}
            self._water_supplies = {ws["id"]: ws for ws in data.get("water_supplies", [])}
            self._programs = {p["id"]: dict(p) for p in data.get("programs", [])}
            self._active_program = data.get("active_program")
            # Restore enabled state + backfill skip_until for pre-existing data
            for pid in self._programs:
                self._programs[pid]["enabled"] = pid == self._active_program
                self._programs[pid].setdefault("skip_until", None)
            _LOGGER.info(
                "Loaded %d valves, %d zones, %d water supplies, %d programs from storage",
                len(self._valves),
                len(self._zones),
                len(self._water_supplies),
                len(self._programs),
            )
        else:
            _LOGGER.info("No stored data found, starting fresh")

    async def _async_save(self) -> None:
        """Persist valves, zones, programs, and active_program to .storage."""
        data = {
            "valves": list(self._valves.values()),
            "zones": list(self._zones.values()),
            "water_supplies": list(self._water_supplies.values()),
            "programs": list(self._programs.values()),
            "active_program": self._active_program,
        }
        await self._store.async_save(data)

    # --- State accessors ---

    @property
    def valves(self) -> dict[str, dict]:
        return self._valves

    @property
    def zones(self) -> dict[str, dict]:
        return self._zones

    @property
    def water_supplies(self) -> dict[str, dict]:
        return self._water_supplies

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
        if self._status == "error":
            return {
                "current_program": self._current_program,
                "active_valves": [],
                "valves_done": None,
                "valves_total": None,
                "progress_percent": None,
                "valves_sequence": None,
                "dry_run": None,
                "error_message": self._error_message,
            }

        if self._status != "running":
            return {
                "current_program": None,
                "active_valves": [],
                "valves_done": None,
                "valves_total": None,
                "progress_percent": None,
                "valves_sequence": None,
                "dry_run": None,
                "error_message": None,
            }

        total = self._valves_total if self._valves_total else 1
        progress = int((self._valves_done / total) * 100)

        return {
            "current_program": self._current_program,
            "active_valves": [dict(e) for e in self._active_valves],
            "valves_done": self._valves_done,
            "valves_total": self._valves_total,
            "progress_percent": progress,
            "valves_sequence": [dict(e) for e in self._valves_sequence],
            "dry_run": self._dry_run,
            "error_message": None,
        }

    # --- Listeners ---

    def add_listener(self, callback) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback) -> None:
        self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        for callback in self._listeners:
            callback()

    def set_entity_callbacks(self, add_callback, remove_callback) -> None:
        """Set callbacks for dynamic entity add/remove."""
        self._add_entities_callback = add_callback
        self._remove_entity_callback = remove_callback

    # --- Valves ---

    async def async_set_valves(self, valves: list[dict]) -> None:
        """Replace all valves. Match by entity_id to preserve existing IDs."""
        existing_by_entity = {v["entity_id"]: v for v in self._valves.values()}

        new_valves: dict[str, dict] = {}
        for valve_data in valves:
            entity_id = valve_data["entity_id"]
            name = valve_data["name"]
            water_supply_id = valve_data.get("water_supply_id")
            zone_id = valve_data.get("zone_id")

            if water_supply_id is not None and water_supply_id not in self._water_supplies:
                raise ValueError(
                    f"Unknown water supply '{water_supply_id}' for valve '{entity_id}'"
                )
            if zone_id is not None and zone_id not in self._zones:
                raise ValueError(f"Unknown zone '{zone_id}' for valve '{entity_id}'")

            if entity_id in existing_by_entity:
                vid = existing_by_entity[entity_id]["id"]
            else:
                vid = entity_id.split(".", 1)[-1] if "." in entity_id else entity_id
                base_vid = vid
                counter = 2
                while vid in new_valves:
                    vid = f"{base_vid}_{counter}"
                    counter += 1

            new_valves[vid] = {
                "id": vid,
                "name": name,
                "entity_id": entity_id,
                "water_supply_id": water_supply_id,
                "zone_id": zone_id,
            }

        self._valves = new_valves
        await self._async_save()
        self._notify_listeners()
        _LOGGER.info("Valves updated: %d valves configured", len(new_valves))

    # --- CRUD: Zones ---

    async def async_create_zone(self, zone_id: str, name: str) -> None:
        """Create a new zone (name only)."""
        if zone_id in self._zones:
            raise ValueError(f"Zone '{zone_id}' already exists")
        self._zones[zone_id] = {"id": zone_id, "name": name}
        await self._async_save()
        self._notify_listeners()
        _LOGGER.info("Zone '%s' created", zone_id)

    async def async_update_zone(self, zone_id: str, name: str | None = None) -> None:
        """Update an existing zone."""
        if zone_id not in self._zones:
            raise ValueError(f"Zone '{zone_id}' not found")
        if name is not None:
            self._zones[zone_id]["name"] = name
        await self._async_save()
        self._notify_listeners()
        _LOGGER.info("Zone '%s' updated", zone_id)

    async def async_delete_zone(self, zone_id: str) -> None:
        """Delete a zone. Clears zone_id on valves that referenced it."""
        if zone_id not in self._zones:
            raise ValueError(f"Zone '{zone_id}' not found")
        for valve in self._valves.values():
            if valve.get("zone_id") == zone_id:
                valve["zone_id"] = None
        del self._zones[zone_id]
        await self._async_save()
        self._notify_listeners()
        _LOGGER.info("Zone '%s' deleted", zone_id)

    # --- CRUD: Water Supplies ---

    async def async_create_water_supply(self, ws_id: str, name: str) -> None:
        """Create a new water supply."""
        if ws_id in self._water_supplies:
            raise ValueError(f"Water supply '{ws_id}' already exists")
        self._water_supplies[ws_id] = {"id": ws_id, "name": name}
        await self._async_save()
        self._notify_listeners()
        _LOGGER.info("Water supply '%s' created", ws_id)

    async def async_update_water_supply(self, ws_id: str, name: str | None = None) -> None:
        """Update an existing water supply."""
        if ws_id not in self._water_supplies:
            raise ValueError(f"Water supply '{ws_id}' not found")
        if name is not None:
            self._water_supplies[ws_id]["name"] = name
        await self._async_save()
        self._notify_listeners()
        _LOGGER.info("Water supply '%s' updated", ws_id)

    async def async_delete_water_supply(self, ws_id: str) -> None:
        """Delete a water supply. Clears water_supply_id on valves that referenced it."""
        if ws_id not in self._water_supplies:
            raise ValueError(f"Water supply '{ws_id}' not found")
        for valve in self._valves.values():
            if valve.get("water_supply_id") == ws_id:
                valve["water_supply_id"] = None
        del self._water_supplies[ws_id]
        await self._async_save()
        self._notify_listeners()
        _LOGGER.info("Water supply '%s' deleted", ws_id)

    # --- CRUD: Programs ---

    def _validate_program_references(self, zones: list[dict]) -> None:
        """Validate that program zone/valve references exist."""
        for zone_ref in zones:
            zone_id = zone_ref["zone_id"]
            if zone_id not in self._zones:
                raise ValueError(f"Unknown zone '{zone_id}'")
            zone_valve_ids = {vid for vid, v in self._valves.items() if v.get("zone_id") == zone_id}
            for valve_ref in zone_ref.get("valves", []):
                vid = valve_ref["valve_id"]
                if vid not in self._valves:
                    raise ValueError(f"Unknown valve '{vid}'")
                if vid not in zone_valve_ids:
                    raise ValueError(f"Valve '{vid}' is not in zone '{zone_id}'")

    async def async_create_program(
        self,
        program_id: str,
        name: str,
        schedule: dict,
        zones: list[dict],
        *,
        dry_run: bool = False,
    ) -> None:
        """Create a new program."""
        if program_id in self._programs:
            raise ValueError(f"Program '{program_id}' already exists")
        self._validate_program_references(zones)
        program = {
            "id": program_id,
            "name": name,
            "enabled": False,
            "dry_run": dry_run,
            "skip_until": None,
            "schedule": schedule,
            "zones": zones,
        }
        self._programs[program_id] = program
        await self._async_save()
        # Dynamically add the switch entity
        if self._add_entities_callback:
            self._add_entities_callback(program_id, program)
        self._notify_listeners()
        _LOGGER.info("Program '%s' created", program_id)

    async def async_update_program(
        self,
        program_id: str,
        name: str | None = None,
        schedule: dict | None = None,
        zones: list[dict] | None = None,
        dry_run: bool | None = None,
    ) -> None:
        """Update an existing program."""
        if program_id not in self._programs:
            raise ValueError(f"Program '{program_id}' not found")
        prog = self._programs[program_id]
        if name is not None:
            prog["name"] = name
        if schedule is not None:
            prog["schedule"] = schedule
        if zones is not None:
            self._validate_program_references(zones)
            prog["zones"] = zones
        if dry_run is not None:
            prog["dry_run"] = dry_run
        await self._async_save()
        self._recalculate_next_run()
        self._notify_listeners()
        _LOGGER.info("Program '%s' updated", program_id)

    async def async_delete_program(self, program_id: str) -> None:
        """Delete a program."""
        if program_id not in self._programs:
            raise ValueError(f"Program '{program_id}' not found")
        if self._running_program == program_id:
            await self.async_stop_all()
        was_active = self._active_program == program_id
        del self._programs[program_id]
        if was_active:
            self._active_program = None
        # Dynamically remove the switch entity
        if self._remove_entity_callback:
            self._remove_entity_callback(program_id)
        await self._async_save()
        self._recalculate_next_run()
        self._notify_listeners()
        _LOGGER.info("Program '%s' deleted", program_id)

    async def async_skip_program(self, program_id: str, days: int) -> None:
        """Skip a program for N days (0 clears skip)."""
        if program_id not in self._programs:
            raise ValueError(f"Program '{program_id}' not found")
        if not self._programs[program_id]["enabled"]:
            raise ValueError(f"Program '{program_id}' is not enabled")

        if days == 0:
            self._programs[program_id]["skip_until"] = None
            _LOGGER.info("Program '%s' skip cleared", program_id)
        else:
            skip_until = (dt_util.now().date() + timedelta(days=days)).isoformat()
            self._programs[program_id]["skip_until"] = skip_until
            _LOGGER.info("Program '%s' skipped until %s", program_id, skip_until)

        await self._async_save()
        self._recalculate_next_run()
        self._notify_listeners()

    # --- Program details (for switch attributes) ---

    def get_program_details(self, program_id: str) -> dict:
        """Resolve a program's zones and valves into full details with names."""
        program = self._programs.get(program_id, {})
        zones = []
        supply_durations: dict[str, int] = {}

        for zone_ref in program.get("zones", []):
            zone = self._zones.get(zone_ref["zone_id"])
            if not zone:
                continue
            valves = []
            for valve_ref in zone_ref.get("valves", []):
                valve = self._valves.get(valve_ref["valve_id"])
                if not valve:
                    continue
                valve_detail: dict = {
                    "valve_id": valve_ref["valve_id"],
                    "valve_name": valve["name"],
                    "duration": valve_ref["duration"],
                }
                if "frequency" in valve_ref:
                    valve_detail["frequency"] = valve_ref["frequency"]
                if "times" in valve_ref:
                    valve_detail["times"] = sorted(valve_ref["times"])
                valves.append(valve_detail)
                supply_id = valve.get("water_supply_id", "")
                supply_durations[supply_id] = (
                    supply_durations.get(supply_id, 0) + valve_ref["duration"]
                )
            zones.append(
                {
                    "zone_id": zone_ref["zone_id"],
                    "zone_name": zone["name"],
                    "valves": valves,
                }
            )

        total_duration = max(supply_durations.values()) if supply_durations else 0

        return {
            "program_id": program_id,
            "schedule": program.get("schedule", {}),
            "zones": zones,
            "total_duration": total_duration,
            "dry_run": program.get("dry_run", False),
            "skip_until": program.get("skip_until"),
        }

    # --- Mutex ---

    async def async_enable_program(self, program_id: str) -> None:
        """Enable a program, disabling all others (mutex)."""
        if self._running_program and self._running_program != program_id:
            await self.async_stop_all()

        for pid in self._programs:
            self._programs[pid]["enabled"] = pid == program_id

        self._active_program = program_id
        await self._async_save()
        self._recalculate_next_run()
        self._notify_listeners()
        _LOGGER.info("Program '%s' enabled", program_id)

    async def async_disable_program(self, program_id: str) -> None:
        """Disable a specific program."""
        if program_id not in self._programs:
            raise ValueError(f"Program '{program_id}' not found")
        self._programs[program_id]["enabled"] = False

        if self._running_program == program_id:
            await self.async_stop_all()

        if self._active_program == program_id:
            self._active_program = None

        await self._async_save()
        self._recalculate_next_run()
        self._notify_listeners()
        _LOGGER.info("Program '%s' disabled", program_id)

    async def async_stop_all(self) -> None:
        """Stop any running program and close all valves."""
        self._cancel_event.set()
        dry_run = self._dry_run
        self._running_program = None
        self._active_valves = []

        # Only reset to idle if not in error state
        if self._status != "error":
            self._status = "idle"

        if not dry_run:
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
        _LOGGER.info(
            "%s execution stopped",
            "[DRY RUN]" if dry_run else "All valves closed,",
        )

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
        # Keep next_run up to date
        self._recalculate_next_run()
        self._notify_listeners()

        if self._running_program:
            return

        active = self._get_active_program()
        if not active:
            return

        # Check skip_until: skip execution or auto-clear if expired
        skip_until_str = active.get("skip_until")
        if skip_until_str:
            today = dt_util.now().date()
            skip_date = date.fromisoformat(skip_until_str)
            if today < skip_date:
                return
            # Skip period expired — auto-clear and resume
            active["skip_until"] = None
            await self._async_save()
            self._recalculate_next_run()
            self._notify_listeners()
            _LOGGER.info("Program '%s' skip expired, resuming", active["id"])

        times = active["schedule"].get("times", [])
        current_time = now.strftime("%H:%M")

        if current_time not in times:
            return

        _LOGGER.info("Triggering program '%s' at %s", active["id"], current_time)
        await self.async_run_program(active["id"], trigger_time=current_time)

    def _get_active_program(self) -> dict | None:
        """Return the single enabled program, or None."""
        for program in self._programs.values():
            if program["enabled"]:
                return program
        return None

    @staticmethod
    def _check_frequency(frequency: dict, now) -> bool:
        """Check if a valve frequency matches today."""
        freq_type = frequency.get("type")

        if freq_type == "weekdays":
            current_weekday: int = now.weekday()
            allowed_days = frequency.get("days", [])
            return bool(current_weekday in [DAY_MAP[d] for d in allowed_days if d in DAY_MAP])

        if freq_type == "every_n_days":
            n = frequency.get("n", 1)
            start_str = frequency.get("start_date")
            if not start_str:
                return True
            start_date = date.fromisoformat(start_str)
            today = now.date() if hasattr(now, "date") else now
            delta: int = (today - start_date).days
            return bool(delta >= 0 and delta % n == 0)

        return True

    def _recalculate_next_run(self) -> None:
        """Recalculate the next_run datetime based on the active program.

        The program can have multiple trigger times per day. next_run is the
        earliest future occurrence across all of them. Valve-level frequency
        filtering happens at execution time.
        """
        active = self._get_active_program()
        if not active:
            self._next_run = None
            return

        times = active["schedule"].get("times", [])
        if not times:
            self._next_run = None
            return

        now = dt_util.now()
        candidates = []
        for t in times:
            hour, minute = map(int, t.split(":"))
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            candidates.append(candidate)

        next_candidate = min(candidates)

        # If skip is active, advance to skip_until date (keep earliest time of day)
        skip_until_str = active.get("skip_until")
        if skip_until_str:
            skip_date = date.fromisoformat(skip_until_str)
            if next_candidate.date() < skip_date:
                next_candidate = next_candidate.replace(
                    year=skip_date.year,
                    month=skip_date.month,
                    day=skip_date.day,
                )

        self._next_run = next_candidate

    # --- Executor ---

    def _build_valves_sequence(
        self, program: dict, now, trigger_time: str | None = None
    ) -> list[dict]:
        """Build the ordered list of eligible valves for this execution.

        Filters by per-valve `frequency` (daily/every_n_days/weekdays) and by
        per-valve `times` (only include valves whose times contains trigger_time,
        or that have no times override).
        """
        sequence = []
        for zone_ref in program.get("zones", []):
            zone = self._zones.get(zone_ref["zone_id"])
            zone_name = zone["name"] if zone else zone_ref["zone_id"]
            for valve_ref in zone_ref.get("valves", []):
                frequency = valve_ref.get("frequency")
                if frequency and not self._check_frequency(frequency, now):
                    _LOGGER.debug(
                        "Valve '%s' skipped (frequency not matched today)",
                        valve_ref["valve_id"],
                    )
                    continue
                valve_times = valve_ref.get("times")
                if trigger_time and valve_times and trigger_time not in valve_times:
                    _LOGGER.debug(
                        "Valve '%s' skipped (trigger time %s not in valve times %s)",
                        valve_ref["valve_id"],
                        trigger_time,
                        valve_times,
                    )
                    continue
                valve = self._valves.get(valve_ref["valve_id"])
                sequence.append(
                    {
                        "valve_id": valve_ref["valve_id"],
                        "valve_name": valve["name"] if valve else valve_ref["valve_id"],
                        "zone_id": zone_ref["zone_id"],
                        "zone_name": zone_name,
                        "duration": valve_ref["duration"] * 60,
                        "water_supply_id": valve["water_supply_id"] if valve else None,
                        "status": "pending",
                    }
                )
        return sequence

    @staticmethod
    def _group_by_supply(sequence: list[dict]) -> dict[str, list[dict]]:
        """Group valve sequence entries by water_supply_id, preserving order."""
        groups: dict[str, list[dict]] = {}
        for entry in sequence:
            groups.setdefault(entry["water_supply_id"], []).append(entry)
        return groups

    async def async_run_program(self, program_id: str, trigger_time: str | None = None) -> None:
        """Execute a program: run supply pipelines in parallel.

        If trigger_time is provided (e.g. "06:00"), per-valve `times` filtering
        is applied: valves with a `times` list that doesn't include trigger_time
        are skipped. If trigger_time is None (manual invocation), per-valve
        times filter is bypassed — all valves run.
        """
        async with self._run_lock:
            if self._running_program:
                _LOGGER.warning("Program execution already in progress, skipping")
                return

            program = self._programs.get(program_id)
            if not program:
                _LOGGER.error("Program '%s' not found", program_id)
                return

            self._cancel_event.clear()
            self._dry_run = program.get("dry_run", False)
            self._error_message = None

            now = dt_util.now()
            sequence = self._build_valves_sequence(program, now, trigger_time)

            if not sequence:
                _LOGGER.info(
                    "Program '%s' triggered but no valves eligible today, skipping",
                    program_id,
                )
                return

            self._running_program = program_id
            self._current_program = program_id
            self._status = "running"
            self._valves_done = 0
            self._valves_total = len(sequence)
            self._valves_sequence = sequence
            self._active_valves = []
            self._notify_listeners()

            self.hass.bus.async_fire(
                EVENT_TYPE,
                {"action": "program_started", "program": program_id},
            )

            try:
                # Group by supply and run pipelines concurrently
                supply_groups = self._group_by_supply(sequence)
                tasks = [
                    self._async_run_pipeline(supply_id, entries)
                    for supply_id, entries in supply_groups.items()
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Check for errors in any pipeline
                errors = [r for r in results if isinstance(r, Exception)]
                if errors:
                    raise errors[0]

                self._status = "idle"
                self._last_run = dt_util.now()
                self._recalculate_next_run()

                self.hass.bus.async_fire(
                    EVENT_TYPE,
                    {"action": "program_finished", "program": program_id},
                )

            except Exception as err:
                _LOGGER.exception("Error running program '%s'", program_id)
                self._error_message = str(err)
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

                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "WateringHub — Erreur",
                        "message": (
                            f"Le programme **{program.get('name', program_id)}** "
                            f"a rencontré une erreur : {err}\n\n"
                            "Toutes les vannes ont été fermées automatiquement."
                        ),
                        "notification_id": "wateringhub_error",
                    },
                )

            finally:
                self._running_program = None
                if self._status != "error":
                    self._current_program = None
                self._active_valves = []
                self._valves_done = 0
                self._valves_total = 0
                self._valves_sequence = []
                self._dry_run = False
                self._notify_listeners()

    async def _async_run_pipeline(self, supply_id: str, entries: list[dict]) -> None:
        """Run a single supply pipeline: its valves sequentially."""
        try:
            for entry in entries:
                if self._cancel_event.is_set():
                    _LOGGER.info("Pipeline '%s' cancelled", supply_id)
                    return

                valve = self._valves.get(entry["valve_id"])
                if not valve:
                    _LOGGER.warning("Valve '%s' not found, skipping", entry["valve_id"])
                    continue

                await self._async_run_valve(valve, entry["duration"] // 60, entry)
                self._valves_done += 1
                entry["status"] = "done"
                self._notify_listeners()
        except Exception:
            self._cancel_event.set()
            raise

    async def _async_run_valve(self, valve: dict, duration_minutes: int, entry: dict) -> None:
        """Open a valve, wait for duration, close it."""
        entity_id = valve["entity_id"]
        valve_id = valve["id"]
        duration_seconds = duration_minutes * 60
        dry_run = self._dry_run

        # Mark running in sequence + add to active_valves
        start_time = dt_util.now()
        entry["status"] = "running"
        entry["start"] = start_time.isoformat()
        active_entry = {
            "water_supply_id": entry.get("water_supply_id"),
            "valve_id": valve_id,
            "valve_name": valve["name"],
            "valve_start": start_time.isoformat(),
            "valve_duration": duration_seconds,
        }
        self._active_valves.append(active_entry)
        self._notify_listeners()

        _LOGGER.info(
            "%s valve '%s' for %d min",
            "[DRY RUN] Simulating" if dry_run else "Opening",
            valve_id,
            duration_minutes,
        )

        self.hass.bus.async_fire(
            EVENT_TYPE,
            {
                "action": "valve_opened",
                "valve": valve_id,
                "duration": duration_seconds,
                "dry_run": dry_run,
                "water_supply_id": entry.get("water_supply_id"),
            },
        )

        if not dry_run:
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

        if not dry_run:
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": entity_id},
                blocking=True,
            )

        # Remove from active_valves
        if active_entry in self._active_valves:
            self._active_valves.remove(active_entry)

        self.hass.bus.async_fire(
            EVENT_TYPE,
            {"action": "valve_closed", "valve": valve_id, "dry_run": dry_run},
        )

        _LOGGER.info(
            "%s valve '%s'",
            "[DRY RUN] Simulated close" if dry_run else "Closed",
            valve_id,
        )

        # Pause between valves within the same pipeline
        if not self._cancel_event.is_set():
            await asyncio.sleep(VALVE_PAUSE_SECONDS)
