# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""Switch entities for WateringHub programs."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN
from .coordinator import WateringHubCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    _config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up WateringHub program switches."""
    coordinator: WateringHubCoordinator = hass.data[DOMAIN]

    entities = [
        ProgramSwitch(coordinator, program_id, program)
        for program_id, program in coordinator.programs.items()
    ]

    async_add_entities(entities)


class ProgramSwitch(SwitchEntity):
    """A switch that represents a watering program (toggle on/off)."""

    def __init__(
        self,
        coordinator: WateringHubCoordinator,
        program_id: str,
        program: dict,
    ) -> None:
        self._coordinator = coordinator
        self._program_id = program_id
        self._attr_name = program["name"]
        self._attr_unique_id = f"{DOMAIN}_{program_id}"
        self.entity_id = f"switch.{DOMAIN}_{program_id}"

    @property
    def is_on(self) -> bool:
        return bool(self._coordinator.programs[self._program_id]["enabled"])

    @property
    def extra_state_attributes(self) -> dict:
        return self._coordinator.get_program_details(self._program_id)

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.async_enable_program(self._program_id)

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.async_disable_program(self._program_id)

    async def async_added_to_hass(self) -> None:
        self._coordinator.add_listener(self.async_schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_listener(self.async_schedule_update_ha_state)
