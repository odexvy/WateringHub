# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""WateringHub coordinator — central logic for scheduling, execution, and mutex."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import DOMAIN, EVENT_TYPE

_LOGGER = logging.getLogger(__name__)


class WateringHubCoordinator:
    """Central coordinator for WateringHub."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        self.hass = hass
        self._valves: dict[str, dict] = {v["id"]: v for v in config["valves"]}
        self._zones: dict[str, dict] = {z["id"]: z for z in config["zones"]}
        self._programs: dict[str, dict] = {p["id"]: dict(p) for p in config["programs"]}

        self._running_program: str | None = None
        self._status: str = "idle"
        self._listeners: list = []

    # --- State accessors ---

    @property
    def programs(self) -> dict[str, dict]:
        return self._programs

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_run(self):
        return None

    @property
    def next_run(self):
        return None

    @property
    def running_program(self) -> str | None:
        return self._running_program

    # --- Listeners (like React Context subscribers) ---

    def add_listener(self, callback) -> None:
        self._listeners.append(callback)

    def remove_listener(self, callback) -> None:
        self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        for callback in self._listeners:
            callback()

    # --- Mutex ---

    async def async_enable_program(self, program_id: str) -> None:
        for pid in self._programs:
            self._programs[pid]["enabled"] = pid == program_id
        self._notify_listeners()
        _LOGGER.info("Program '%s' enabled", program_id)

    async def async_disable_program(self, program_id: str) -> None:
        self._programs[program_id]["enabled"] = False
        self._notify_listeners()
        _LOGGER.info("Program '%s' disabled", program_id)

    async def async_stop_all(self) -> None:
        self._running_program = None
        self._status = "idle"
        for valve in self._valves.values():
            try:
                await self.hass.services.async_call(
                    "switch", "turn_off",
                    {"entity_id": valve["entity_id"]},
                    blocking=True,
                )
            except Exception:
                _LOGGER.exception("Failed to close valve '%s'", valve["id"])
        self._notify_listeners()
        _LOGGER.info("All valves closed")

    async def async_start(self) -> None:
        _LOGGER.info("WateringHub coordinator started (minimal mode)")
