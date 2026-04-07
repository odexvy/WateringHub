# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""The WateringHub integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .coordinator import WateringHubCoordinator

_LOGGER = logging.getLogger(__name__)

VALVE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Required("entity_id"): cv.string,
        vol.Optional("flow_sensor"): cv.string,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("valves"): vol.All(cv.ensure_list, [VALVE_SCHEMA]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

# --- Service schemas ---

CREATE_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Required("valves"): vol.All(cv.ensure_list, [cv.string]),
    }
)

UPDATE_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("valves"): vol.All(cv.ensure_list, [cv.string]),
    }
)

DELETE_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
    }
)

PROGRAM_VALVE_SCHEMA = vol.Schema(
    {
        vol.Required("valve_id"): cv.string,
        vol.Required("duration"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)

PROGRAM_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("zone_id"): cv.string,
        vol.Required("valves"): vol.All(cv.ensure_list, [PROGRAM_VALVE_SCHEMA]),
    }
)

SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In(["daily", "every_n_days", "weekdays"]),
        vol.Required("time"): cv.string,
        vol.Optional("n"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("days"): vol.All(
            cv.ensure_list,
            [vol.In(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])],
        ),
        vol.Optional("start_date"): cv.string,
    }
)

CREATE_PROGRAM_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Required("schedule"): SCHEDULE_SCHEMA,
        vol.Required("zones"): vol.All(cv.ensure_list, [PROGRAM_ZONE_SCHEMA]),
        vol.Optional("dry_run", default=False): cv.boolean,
    }
)

UPDATE_PROGRAM_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("schedule"): SCHEDULE_SCHEMA,
        vol.Optional("zones"): vol.All(cv.ensure_list, [PROGRAM_ZONE_SCHEMA]),
        vol.Optional("dry_run"): cv.boolean,
    }
)

DELETE_PROGRAM_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up WateringHub from YAML configuration."""
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    valves = {v["id"]: v for v in conf["valves"]}

    try:
        coordinator = WateringHubCoordinator(hass, valves)
        await coordinator.async_load()
        hass.data[DOMAIN] = coordinator

        for platform in PLATFORMS:
            await async_load_platform(hass, platform, DOMAIN, {}, config)

        # --- Register services ---

        async def handle_stop_all(_call: ServiceCall) -> None:
            await coordinator.async_stop_all()

        async def handle_create_zone(call: ServiceCall) -> None:
            await coordinator.async_create_zone(
                call.data["id"],
                call.data["name"],
                call.data["valves"],
            )

        async def handle_update_zone(call: ServiceCall) -> None:
            await coordinator.async_update_zone(
                call.data["id"],
                name=call.data.get("name"),
                valves=call.data.get("valves"),
            )

        async def handle_delete_zone(call: ServiceCall) -> None:
            await coordinator.async_delete_zone(call.data["id"])

        async def handle_create_program(call: ServiceCall) -> None:
            await coordinator.async_create_program(
                call.data["id"],
                call.data["name"],
                call.data["schedule"],
                call.data["zones"],
                dry_run=call.data.get("dry_run", False),
            )

        async def handle_update_program(call: ServiceCall) -> None:
            await coordinator.async_update_program(
                call.data["id"],
                name=call.data.get("name"),
                schedule=call.data.get("schedule"),
                zones=call.data.get("zones"),
                dry_run=call.data.get("dry_run"),
            )

        async def handle_delete_program(call: ServiceCall) -> None:
            await coordinator.async_delete_program(call.data["id"])

        hass.services.async_register(DOMAIN, "stop_all", handle_stop_all)
        hass.services.async_register(
            DOMAIN, "create_zone", handle_create_zone, schema=CREATE_ZONE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, "update_zone", handle_update_zone, schema=UPDATE_ZONE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, "delete_zone", handle_delete_zone, schema=DELETE_ZONE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, "create_program", handle_create_program, schema=CREATE_PROGRAM_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, "update_program", handle_update_program, schema=UPDATE_PROGRAM_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, "delete_program", handle_delete_program, schema=DELETE_PROGRAM_SCHEMA
        )

        async def handle_shutdown(_event) -> None:
            await coordinator.async_stop()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, handle_shutdown)

        coordinator.start()
    except Exception:
        _LOGGER.exception("Failed to set up WateringHub")
        return False

    return True
