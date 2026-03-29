# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""The WateringHub integration."""
from __future__ import annotations

import logging
import re

import voluptuous as vol
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import WateringHubCoordinator

_LOGGER = logging.getLogger(__name__)


def _validate_time(value: str) -> str:
    """Validate HH:MM time format."""
    if not re.match(r"^\d{2}:\d{2}$", value):
        raise vol.Invalid(f"Invalid time format '{value}', expected HH:MM")
    hour, minute = map(int, value.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise vol.Invalid(f"Invalid time '{value}', hour must be 0-23 and minute 0-59")
    return value


def _validate_date(value: str) -> str:
    """Validate ISO date format (YYYY-MM-DD)."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        raise vol.Invalid(f"Invalid date format '{value}', expected YYYY-MM-DD")
    from datetime import date
    try:
        date.fromisoformat(value)
    except ValueError as err:
        raise vol.Invalid(f"Invalid date '{value}': {err}") from err
    return value


VALVE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Required("entity_id"): cv.string,
        vol.Optional("flow_sensor"): cv.string,
    }
)

ZONE_VALVE_SCHEMA = vol.Schema(
    {
        vol.Required("valve_id"): cv.string,
        vol.Required("duration"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)

ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Required("valves"): vol.All(cv.ensure_list, [ZONE_VALVE_SCHEMA]),
    }
)

SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In(["daily", "every_n_days", "weekdays"]),
        vol.Required("time"): _validate_time,
        vol.Optional("n"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("days"): vol.All(cv.ensure_list, [vol.In(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])]),
        vol.Optional("start_date"): _validate_date,
    }
)

PROGRAM_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("zone_id"): cv.string,
    }
)

PROGRAM_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Required("enabled"): cv.boolean,
        vol.Required("schedule"): SCHEDULE_SCHEMA,
        vol.Required("zones"): vol.All(cv.ensure_list, [PROGRAM_ZONE_SCHEMA]),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("valves"): vol.All(cv.ensure_list, [VALVE_SCHEMA]),
                vol.Required("zones"): vol.All(cv.ensure_list, [ZONE_SCHEMA]),
                vol.Required("programs"): vol.All(cv.ensure_list, [PROGRAM_SCHEMA]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def _validate_cross_references(conf: dict) -> None:
    """Validate that zones reference existing valves and programs reference existing zones."""
    valve_ids = {v["id"] for v in conf["valves"]}
    zone_ids = {z["id"] for z in conf["zones"]}

    for zone in conf["zones"]:
        for valve_ref in zone["valves"]:
            if valve_ref["valve_id"] not in valve_ids:
                raise vol.Invalid(
                    f"Zone '{zone['id']}' references unknown valve '{valve_ref['valve_id']}'"
                )

    for program in conf["programs"]:
        for zone_ref in program["zones"]:
            if zone_ref["zone_id"] not in zone_ids:
                raise vol.Invalid(
                    f"Program '{program['id']}' references unknown zone '{zone_ref['zone_id']}'"
                )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up WateringHub from YAML configuration."""
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]

    try:
        _validate_cross_references(conf)
    except vol.Invalid as err:
        _LOGGER.error("Invalid WateringHub configuration: %s", err)
        return False

    try:
        coordinator = WateringHubCoordinator(hass, conf)
        hass.data[DOMAIN] = coordinator

        for platform in PLATFORMS:
            await async_load_platform(hass, platform, DOMAIN, {}, config)

        async def handle_stop_all(call: ServiceCall) -> None:
            await coordinator.async_stop_all()

        hass.services.async_register(DOMAIN, "stop_all", handle_stop_all)

        async def handle_shutdown(event) -> None:
            """Clean up on HA shutdown."""
            await coordinator.async_stop()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, handle_shutdown)

        coordinator.start()
    except Exception:
        _LOGGER.exception("Failed to set up WateringHub")
        return False

    return True
