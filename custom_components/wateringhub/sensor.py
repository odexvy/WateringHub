# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""Sensor entities for WateringHub."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import WateringHubCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    _entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up WateringHub sensors."""
    coordinator: WateringHubCoordinator = hass.data[DOMAIN]

    async_add_entities(
        [
            StatusSensor(coordinator),
            NextRunSensor(coordinator),
            LastRunSensor(coordinator),
        ]
    )


class StatusSensor(SensorEntity):
    """Current status: idle, running, error."""

    _attr_should_poll = False

    def __init__(self, coordinator: WateringHubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_name = "WateringHub Status"
        self._attr_unique_id = f"{DOMAIN}_status"

    @property
    def native_value(self) -> str:
        return self._coordinator.status

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **self._coordinator.execution_state,
            "available_valves": list(self._coordinator.valves.values()),
            "zones": list(self._coordinator.zones.values()),
            "water_supplies": list(self._coordinator.water_supplies.values()),
        }

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_schedule_update_ha_state)


class NextRunSensor(SensorEntity):
    """Next scheduled run datetime."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_should_poll = False

    def __init__(self, coordinator: WateringHubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_name = "WateringHub Next Run"
        self._attr_unique_id = f"{DOMAIN}_next_run"

    @property
    def native_value(self):
        return self._coordinator.next_run

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_schedule_update_ha_state)


class LastRunSensor(SensorEntity):
    """Last completed run datetime."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_should_poll = False

    def __init__(self, coordinator: WateringHubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_name = "WateringHub Last Run"
        self._attr_unique_id = f"{DOMAIN}_last_run"

    @property
    def native_value(self):
        return self._coordinator.last_run

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_schedule_update_ha_state)
