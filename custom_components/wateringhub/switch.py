# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""Switch entities for WateringHub programs."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN
from .coordinator import WateringHubCoordinator

_LOGGER = logging.getLogger(__name__)

# Track active switch entities for dynamic add/remove
_program_switches: dict[str, ProgramSwitch] = {}


async def async_setup_platform(
    hass: HomeAssistant,
    _config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    _discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up WateringHub program switches."""
    coordinator: WateringHubCoordinator = hass.data[DOMAIN]

    # Create switches for existing programs (loaded from storage)
    entities = []
    for program_id, program in coordinator.programs.items():
        switch = ProgramSwitch(coordinator, program_id, program)
        _program_switches[program_id] = switch
        entities.append(switch)

    if entities:
        async_add_entities(entities)

    # Register callbacks for dynamic program add/remove
    def add_program_entity(program_id: str, program: dict) -> None:
        switch = ProgramSwitch(coordinator, program_id, program)
        _program_switches[program_id] = switch
        async_add_entities([switch])

    def remove_program_entity(program_id: str) -> None:
        switch = _program_switches.pop(program_id, None)
        if switch:
            hass.async_create_task(_async_remove_entity(hass, switch))

    coordinator.set_entity_callbacks(add_program_entity, remove_program_entity)


async def _async_remove_entity(hass: HomeAssistant, switch: ProgramSwitch) -> None:
    """Remove a switch entity from HA."""
    entity_registry = async_get_entity_registry(hass)
    entity_id = switch.entity_id
    if entity_registry.async_get(entity_id):
        entity_registry.async_remove(entity_id)
        _LOGGER.info("Removed entity %s", entity_id)


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
        return bool(self._coordinator.programs.get(self._program_id, {}).get("enabled", False))

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
