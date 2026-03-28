# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""The WateringHub integration."""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS
from .coordinator import WateringHubCoordinator

_LOGGER = logging.getLogger(__name__)

VALVE_SCHEMA = vol.Schema(
    {
        vol.Required("id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("flow_sensor"): cv.entity_id,
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
        vol.Required("time"): cv.string,
        vol.Optional("n"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("days"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("start_date"): cv.string,
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up WateringHub from YAML configuration."""
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    coordinator = WateringHubCoordinator(hass, conf)
    hass.data[DOMAIN] = coordinator

    for platform in PLATFORMS:
        hass.async_create_task(
            hass.helpers.discovery.async_load_platform(
                platform, DOMAIN, {}, config
            )
        )

    async def handle_stop_all(call: ServiceCall) -> None:
        await coordinator.async_stop_all()

    hass.services.async_register(DOMAIN, "stop_all", handle_stop_all)

    await coordinator.async_start()

    return True
