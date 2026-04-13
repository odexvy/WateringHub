# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""The WateringHub integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS
from .coordinator import WateringHubCoordinator

_LOGGER = logging.getLogger(__name__)

# --- Service schemas ---

CREATE_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Required("name"): cv.string,
    }
)

UPDATE_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Optional("name"): cv.string,
    }
)

DELETE_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
    }
)

CREATE_WATER_SUPPLY_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Required("name"): cv.string,
    }
)

UPDATE_WATER_SUPPLY_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Optional("name"): cv.string,
    }
)

DELETE_WATER_SUPPLY_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
    }
)

VALVE_FREQUENCY_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In(["every_n_days", "weekdays"]),
        vol.Optional("n"): vol.All(vol.Coerce(int), vol.Range(min=2)),
        vol.Optional("days"): vol.All(
            cv.ensure_list,
            [vol.In(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])],
        ),
        vol.Optional("start_date"): cv.string,
    }
)

PROGRAM_VALVE_SCHEMA = vol.Schema(
    {
        vol.Required("valve_id"): cv.string,
        vol.Required("duration"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("frequency"): VALVE_FREQUENCY_SCHEMA,
    }
)

PROGRAM_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required("zone_id"): cv.string,
        vol.Required("valves"): vol.All(cv.ensure_list, [PROGRAM_VALVE_SCHEMA]),
    }
)

SCHEDULE_SCHEMA = vol.Schema(
    {vol.Required("time"): cv.string},
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

SKIP_PROGRAM_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Required("days"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)

SET_VALVE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Optional("water_supply_id"): vol.Any(cv.string, None),
        vol.Optional("zone_id"): vol.Any(cv.string, None),
    }
)

SET_VALVES_SCHEMA = vol.Schema(
    {
        vol.Required("valves"): vol.All(cv.ensure_list, [SET_VALVE_SCHEMA]),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up WateringHub from a config entry."""
    coordinator = WateringHubCoordinator(hass)
    await coordinator.async_load()
    hass.data[DOMAIN] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- Register services ---

    async def handle_stop_all(_call: ServiceCall) -> None:
        await coordinator.async_stop_all()

    async def handle_set_valves(call: ServiceCall) -> None:
        await coordinator.async_set_valves(call.data["valves"])

    async def handle_create_zone(call: ServiceCall) -> None:
        await coordinator.async_create_zone(
            call.data["id"],
            call.data["name"],
        )

    async def handle_update_zone(call: ServiceCall) -> None:
        await coordinator.async_update_zone(
            call.data["id"],
            name=call.data.get("name"),
        )

    async def handle_delete_zone(call: ServiceCall) -> None:
        await coordinator.async_delete_zone(call.data["id"])

    async def handle_create_water_supply(call: ServiceCall) -> None:
        await coordinator.async_create_water_supply(
            call.data["id"],
            call.data["name"],
        )

    async def handle_update_water_supply(call: ServiceCall) -> None:
        await coordinator.async_update_water_supply(
            call.data["id"],
            name=call.data.get("name"),
        )

    async def handle_delete_water_supply(call: ServiceCall) -> None:
        await coordinator.async_delete_water_supply(call.data["id"])

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

    async def handle_skip_program(call: ServiceCall) -> None:
        await coordinator.async_skip_program(call.data["id"], call.data["days"])

    hass.services.async_register(DOMAIN, "stop_all", handle_stop_all)
    hass.services.async_register(DOMAIN, "set_valves", handle_set_valves, schema=SET_VALVES_SCHEMA)
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
        DOMAIN,
        "create_water_supply",
        handle_create_water_supply,
        schema=CREATE_WATER_SUPPLY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "update_water_supply",
        handle_update_water_supply,
        schema=UPDATE_WATER_SUPPLY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "delete_water_supply",
        handle_delete_water_supply,
        schema=DELETE_WATER_SUPPLY_SCHEMA,
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
    hass.services.async_register(
        DOMAIN, "skip_program", handle_skip_program, schema=SKIP_PROGRAM_SCHEMA
    )

    coordinator.start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: WateringHubCoordinator = hass.data[DOMAIN]
    await coordinator.async_stop()

    unload_ok: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.pop(DOMAIN)

    return unload_ok
