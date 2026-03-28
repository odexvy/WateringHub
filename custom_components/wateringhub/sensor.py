# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""Sensor entities for WateringHub."""
from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN
from .coordinator import WateringHubCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up WateringHub sensors."""
    _LOGGER.debug("Setting up WateringHub sensor platform")

    coordinator: WateringHubCoordinator = hass.data[DOMAIN]

    async_add_entities([
        StatusSensor(coordinator),
        NextRunSensor(coordinator),
        LastRunSensor(coordinator),
    ])


class StatusSensor(SensorEntity):
    """Current status: idle, running, error."""

    def __init__(self, coordinator: WateringHubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_name = "WateringHub Status"
        self._attr_unique_id = f"{DOMAIN}_status"

    @property
    def native_value(self) -> str:
        return self._coordinator.status

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_write_ha_state)


class NextRunSensor(SensorEntity):
    """Next scheduled run datetime."""

    def __init__(self, coordinator: WateringHubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_name = "WateringHub Next Run"
        self._attr_unique_id = f"{DOMAIN}_next_run"

    @property
    def native_value(self) -> str | None:
        if self._coordinator.next_run:
            return self._coordinator.next_run.isoformat()
        return None

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_write_ha_state)


class LastRunSensor(SensorEntity):
    """Last completed run datetime."""

    def __init__(self, coordinator: WateringHubCoordinator) -> None:
        self._coordinator = coordinator
        self._attr_name = "WateringHub Last Run"
        self._attr_unique_id = f"{DOMAIN}_last_run"

    @property
    def native_value(self) -> str | None:
        if self._coordinator.last_run:
            return self._coordinator.last_run.isoformat()
        return None

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_write_ha_state)
