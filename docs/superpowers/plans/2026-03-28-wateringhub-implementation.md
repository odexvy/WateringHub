# WateringHub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working Home Assistant custom component (HACS) that manages automated watering with valves, zones, programs, mutex, and scheduling.

**Architecture:** Monolithic Coordinator pattern — a single `WateringHubCoordinator` class handles config parsing, mutex, scheduling, and sequential valve execution. Platforms (`switch.py`, `sensor.py`) expose entities that observe the Coordinator.

**Tech Stack:** Python 3.11+, Home Assistant Core 2024.1+, HACS, no external dependencies.

**Git policy:** Claude is read-only on git. All commit/push steps are for the developer to run.

---

## File Map

| File | Responsibility | Created in |
|---|---|---|
| `hacs.json` | HACS metadata | Task 1 |
| `LICENSE` | MIT license text | Task 1 |
| `custom_components/wateringhub/manifest.json` | HA component metadata | Task 2 |
| `custom_components/wateringhub/const.py` | Domain, event type, constants | Task 2 |
| `custom_components/wateringhub/__init__.py` | Setup, config parsing, service registration, unload | Task 3 |
| `custom_components/wateringhub/coordinator.py` | Mutex, scheduling, execution | Task 4-6 |
| `custom_components/wateringhub/switch.py` | ProgramSwitch entities | Task 7 |
| `custom_components/wateringhub/sensor.py` | Status, NextRun, LastRun sensors | Task 8 |
| `custom_components/wateringhub/services.yaml` | Service schema definitions | Task 3 |
| `custom_components/wateringhub/translations/en.json` | English translations | Task 9 |

---

### Task 1: Root files (hacs.json, LICENSE)

**Files:**
- Create: `hacs.json`
- Create: `LICENSE`

- [ ] **Step 1: Create `hacs.json`**

```json
{
  "name": "WateringHub",
  "hacs": "2.0.0",
  "domains": ["wateringhub"],
  "iot_class": "local_push",
  "homeassistant": "2024.1.0"
}
```

- [ ] **Step 2: Create `LICENSE`**

Standard MIT license file with:
```
MIT License

Copyright (c) 2026 WateringHub contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Commit**

```bash
git add hacs.json LICENSE
git commit -m "feat: add HACS metadata and MIT license"
```

---

### Task 2: manifest.json and const.py

**Files:**
- Create: `custom_components/wateringhub/manifest.json`
- Create: `custom_components/wateringhub/const.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p custom_components/wateringhub/translations
```

- [ ] **Step 2: Create `custom_components/wateringhub/manifest.json`**

```json
{
  "domain": "wateringhub",
  "name": "WateringHub",
  "codeowners": [],
  "dependencies": [],
  "documentation": "https://github.com/your-user/WateringHub",
  "iot_class": "local_push",
  "version": "0.0.1"
}
```

- [ ] **Step 3: Create `custom_components/wateringhub/const.py`**

```python
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""Constants for the WateringHub integration."""

DOMAIN = "wateringhub"
EVENT_TYPE = "wateringhub_event"
PLATFORMS = ["switch", "sensor"]

VALVE_PAUSE_SECONDS = 5
```

- [ ] **Step 4: Commit**

```bash
git add custom_components/
git commit -m "feat: add manifest.json and const.py"
```

---

### Task 3: __init__.py (setup, config parsing, services)

**Files:**
- Create: `custom_components/wateringhub/__init__.py`
- Create: `custom_components/wateringhub/services.yaml`

- [ ] **Step 1: Create `custom_components/wateringhub/services.yaml`**

```yaml
stop_all:
  name: Stop All
  description: Close all valves immediately and cancel any running program.
```

- [ ] **Step 2: Create `custom_components/wateringhub/__init__.py`**

This file parses the YAML config, creates the Coordinator, forwards setup to platforms, and registers the `stop_all` service.

```python
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
        """Handle the stop_all service call."""
        await coordinator.async_stop_all()

    hass.services.async_register(DOMAIN, "stop_all", handle_stop_all)

    await coordinator.async_start()

    return True
```

- [ ] **Step 3: Verify file loads without syntax errors**

Quick check: open the file and verify no obvious issues. The real validation happens when HA loads it.

- [ ] **Step 4: Commit**

```bash
git add custom_components/wateringhub/__init__.py custom_components/wateringhub/services.yaml
git commit -m "feat: add init with config parsing and stop_all service"
```

---

### Task 4: Coordinator — data model and mutex

**Files:**
- Create: `custom_components/wateringhub/coordinator.py`

- [ ] **Step 1: Create `coordinator.py` with data model and mutex logic**

```python
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 WateringHub contributors
"""WateringHub coordinator — central logic for scheduling, execution, and mutex."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, date

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN, EVENT_TYPE, VALVE_PAUSE_SECONDS

_LOGGER = logging.getLogger(__name__)


class WateringHubCoordinator:
    """Central coordinator for WateringHub."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """Initialize the coordinator with parsed config."""
        self.hass = hass
        self._valves: dict[str, dict] = {v["id"]: v for v in config["valves"]}
        self._zones: dict[str, dict] = {z["id"]: z for z in config["zones"]}
        self._programs: dict[str, dict] = {p["id"]: dict(p) for p in config["programs"]}

        self._running_program: str | None = None
        self._cancel_event: asyncio.Event = asyncio.Event()
        self._unsub_time: list = []
        self._listeners: list = []

        self._status: str = "idle"
        self._last_run: datetime | None = None
        self._next_run: datetime | None = None

    # --- State accessors ---

    @property
    def programs(self) -> dict[str, dict]:
        """Return all programs."""
        return self._programs

    @property
    def status(self) -> str:
        """Return current status: idle, running, error."""
        return self._status

    @property
    def last_run(self) -> datetime | None:
        """Return datetime of last completed run."""
        return self._last_run

    @property
    def next_run(self) -> datetime | None:
        """Return datetime of next scheduled run."""
        return self._next_run

    @property
    def running_program(self) -> str | None:
        """Return ID of currently running program, or None."""
        return self._running_program

    # --- Listener pattern (like React Context subscribers) ---

    def add_listener(self, callback) -> None:
        """Register a callback to be called on state changes."""
        self._listeners.append(callback)

    def remove_listener(self, callback) -> None:
        """Remove a previously registered callback."""
        self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        """Notify all registered listeners of a state change."""
        for callback in self._listeners:
            callback()

    # --- Mutex ---

    async def async_enable_program(self, program_id: str) -> None:
        """Enable a program, disabling all others (mutex)."""
        if self._running_program and self._running_program != program_id:
            await self.async_stop_all()

        for pid in self._programs:
            self._programs[pid]["enabled"] = pid == program_id

        self._recalculate_next_run()
        self._notify_listeners()
        _LOGGER.info("Program '%s' enabled", program_id)

    async def async_disable_program(self, program_id: str) -> None:
        """Disable a specific program."""
        self._programs[program_id]["enabled"] = False

        if self._running_program == program_id:
            await self.async_stop_all()

        self._recalculate_next_run()
        self._notify_listeners()
        _LOGGER.info("Program '%s' disabled", program_id)

    async def async_stop_all(self) -> None:
        """Stop any running program and close all valves."""
        self._cancel_event.set()
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
        _LOGGER.info("All valves closed, execution stopped")
```

- [ ] **Step 2: Commit**

```bash
git add custom_components/wateringhub/coordinator.py
git commit -m "feat: add coordinator with data model, mutex, and stop_all"
```

---

### Task 5: Coordinator — scheduling

**Files:**
- Modify: `custom_components/wateringhub/coordinator.py`

- [ ] **Step 1: Add scheduling methods to `WateringHubCoordinator`**

Append these methods to the class in `coordinator.py`:

```python
    # --- Scheduling ---

    async def async_start(self) -> None:
        """Start the scheduler. Called once from async_setup."""
        self._cancel_event.clear()
        self._recalculate_next_run()

        unsub = async_track_time_change(
            self.hass, self._async_time_tick,
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

    async def _async_time_tick(self, now: datetime) -> None:
        """Called every minute. Check if a program should run."""
        if self._running_program:
            return

        active = self._get_active_program()
        if not active:
            return

        schedule = active["schedule"]
        target_time = schedule["time"]
        current_time = now.strftime("%H:%M")

        if current_time != target_time:
            return

        if not self._should_run_today(active, now):
            return

        _LOGGER.info("Triggering program '%s'", active["id"])
        self.hass.async_create_task(self.async_run_program(active["id"]))

    def _get_active_program(self) -> dict | None:
        """Return the single enabled program, or None."""
        for program in self._programs.values():
            if program["enabled"]:
                return program
        return None

    def _should_run_today(self, program: dict, now: datetime) -> bool:
        """Check if a program should run today based on schedule type."""
        schedule = program["schedule"]
        schedule_type = schedule["type"]

        if schedule_type == "daily":
            return True

        if schedule_type == "weekdays":
            day_name = now.strftime("%a").lower()
            return day_name in schedule.get("days", [])

        if schedule_type == "every_n_days":
            n = schedule.get("n", 1)
            start_str = schedule.get("start_date")
            if not start_str:
                return True
            start_date = date.fromisoformat(start_str)
            delta = (now.date() - start_date).days
            return delta >= 0 and delta % n == 0

        return False

    def _recalculate_next_run(self) -> None:
        """Recalculate the next_run datetime based on the active program."""
        from datetime import timedelta

        active = self._get_active_program()
        if not active:
            self._next_run = None
            return

        schedule = active["schedule"]
        hour, minute = map(int, schedule["time"].split(":"))
        now = datetime.now()
        today_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        candidate = today_run
        if candidate <= now:
            candidate += timedelta(days=1)

        # For every_n_days and weekdays, advance until a valid day
        for _ in range(400):
            if self._should_run_today(active, candidate):
                self._next_run = candidate
                return
            candidate += timedelta(days=1)

        self._next_run = None
```

- [ ] **Step 2: Commit**

```bash
git add custom_components/wateringhub/coordinator.py
git commit -m "feat: add scheduling logic to coordinator"
```

---

### Task 6: Coordinator — executor (sequential valve control)

**Files:**
- Modify: `custom_components/wateringhub/coordinator.py`

- [ ] **Step 1: Add execution methods to `WateringHubCoordinator`**

Append these methods to the class in `coordinator.py`:

```python
    # --- Executor ---

    async def async_run_program(self, program_id: str) -> None:
        """Execute a program: run each zone's valves sequentially."""
        program = self._programs.get(program_id)
        if not program:
            _LOGGER.error("Program '%s' not found", program_id)
            return

        self._cancel_event.clear()
        self._running_program = program_id
        self._status = "running"
        self._notify_listeners()

        self.hass.bus.async_fire(EVENT_TYPE, {
            "action": "program_started",
            "program": program_id,
        })

        try:
            for zone_ref in program["zones"]:
                zone = self._zones.get(zone_ref["zone_id"])
                if not zone:
                    _LOGGER.warning("Zone '%s' not found, skipping", zone_ref["zone_id"])
                    continue

                for valve_ref in zone["valves"]:
                    if self._cancel_event.is_set():
                        _LOGGER.info("Execution cancelled")
                        return

                    valve = self._valves.get(valve_ref["valve_id"])
                    if not valve:
                        _LOGGER.warning("Valve '%s' not found, skipping", valve_ref["valve_id"])
                        continue

                    await self._async_run_valve(valve, valve_ref["duration"])

            self._status = "idle"
            self._last_run = datetime.now()
            self._recalculate_next_run()

            self.hass.bus.async_fire(EVENT_TYPE, {
                "action": "program_finished",
                "program": program_id,
            })

        except Exception as err:
            _LOGGER.exception("Error running program '%s'", program_id)
            self._status = "error"
            await self.async_stop_all()

            self.hass.bus.async_fire(EVENT_TYPE, {
                "action": "program_error",
                "program": program_id,
                "error": str(err),
            })

        finally:
            self._running_program = None
            self._notify_listeners()

    async def _async_run_valve(self, valve: dict, duration_minutes: int) -> None:
        """Open a valve, wait for duration, close it."""
        entity_id = valve["entity_id"]
        valve_id = valve["id"]
        duration_seconds = duration_minutes * 60

        _LOGGER.info("Opening valve '%s' for %d min", valve_id, duration_minutes)

        self.hass.bus.async_fire(EVENT_TYPE, {
            "action": "valve_opened",
            "valve": valve_id,
            "duration": duration_seconds,
        })

        await self.hass.services.async_call(
            "switch", "turn_on",
            {"entity_id": entity_id},
            blocking=True,
        )

        # Wait for duration, checking cancel every second
        for _ in range(duration_seconds):
            if self._cancel_event.is_set():
                break
            await asyncio.sleep(1)

        await self.hass.services.async_call(
            "switch", "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

        self.hass.bus.async_fire(EVENT_TYPE, {
            "action": "valve_closed",
            "valve": valve_id,
        })

        _LOGGER.info("Valve '%s' closed", valve_id)

        # Pause between valves
        if not self._cancel_event.is_set():
            await asyncio.sleep(VALVE_PAUSE_SECONDS)
```

- [ ] **Step 2: Commit**

```bash
git add custom_components/wateringhub/coordinator.py
git commit -m "feat: add sequential valve execution to coordinator"
```

---

### Task 7: ProgramSwitch entities

**Files:**
- Create: `custom_components/wateringhub/switch.py`

- [ ] **Step 1: Create `switch.py`**

```python
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
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
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
        """Initialize the program switch."""
        self._coordinator = coordinator
        self._program_id = program_id
        self._attr_name = program["name"]
        self._attr_unique_id = f"{DOMAIN}_{program_id}"

    @property
    def is_on(self) -> bool:
        """Return True if the program is enabled."""
        return self._coordinator.programs[self._program_id]["enabled"]

    async def async_turn_on(self, **kwargs) -> None:
        """Enable this program (mutex: disables all others)."""
        await self._coordinator.async_enable_program(self._program_id)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable this program. Stop execution if running."""
        await self._coordinator.async_disable_program(self._program_id)

    async def async_added_to_hass(self) -> None:
        """Register listener when entity is added to HA."""
        self._coordinator.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Remove listener when entity is removed from HA."""
        self._coordinator.remove_listener(self.async_write_ha_state)
```

- [ ] **Step 2: Commit**

```bash
git add custom_components/wateringhub/switch.py
git commit -m "feat: add ProgramSwitch entities"
```

---

### Task 8: Sensor entities

**Files:**
- Create: `custom_components/wateringhub/sensor.py`

- [ ] **Step 1: Create `sensor.py`**

```python
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
    coordinator: WateringHubCoordinator = hass.data[DOMAIN]

    async_add_entities([
        StatusSensor(coordinator),
        NextRunSensor(coordinator),
        LastRunSensor(coordinator),
    ])


class StatusSensor(SensorEntity):
    """Sensor showing current status: idle, running, error."""

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
    """Sensor showing the next scheduled run datetime."""

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
    """Sensor showing the last completed run datetime."""

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
```

- [ ] **Step 2: Commit**

```bash
git add custom_components/wateringhub/sensor.py
git commit -m "feat: add status, next_run, last_run sensors"
```

---

### Task 9: Translations

**Files:**
- Create: `custom_components/wateringhub/translations/en.json`

- [ ] **Step 1: Create `translations/en.json`**

```json
{
  "title": "WateringHub",
  "services": {
    "stop_all": {
      "name": "Stop All",
      "description": "Close all valves immediately and cancel any running program."
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add custom_components/wateringhub/translations/
git commit -m "feat: add English translations"
```

---

### Task 10: First pre-release and HACS test

- [ ] **Step 1: Verify file structure**

```bash
find custom_components/wateringhub -type f | sort
```

Expected output:
```
custom_components/wateringhub/__init__.py
custom_components/wateringhub/const.py
custom_components/wateringhub/coordinator.py
custom_components/wateringhub/manifest.json
custom_components/wateringhub/sensor.py
custom_components/wateringhub/services.yaml
custom_components/wateringhub/switch.py
custom_components/wateringhub/translations/en.json
```

- [ ] **Step 2: Push and create pre-release**

```bash
git push origin master
gh release create v0.0.1-alpha --title "v0.0.1-alpha — Initial structure" --notes "First testable version with all components wired up." --prerelease
```

- [ ] **Step 3: Test in HACS**

1. HACS → Settings → check "Show beta versions"
2. HACS → Integrations → + → search "WateringHub" (or add custom repository)
3. Install → restart HA
4. Add to `configuration.yaml`:

```yaml
wateringhub:
  valves:
    - id: cedre
      name: Oscillant Cèdre
      entity_id: switch.0xe406bffffed0fdc0
      flow_sensor: sensor.0xe406bffffed0fdc0_flow
    - id: terrasse
      name: Oscillant Terrasse
      entity_id: switch.0xe406bffffed10058
      flow_sensor: sensor.0xe406bffffed10058_flow

  zones:
    - id: jardin
      name: Jardin complet
      valves:
        - valve_id: cedre
          duration: 15
        - valve_id: terrasse
          duration: 20

  programs:
    - id: prog_quotidien
      name: Arrosage quotidien
      enabled: true
      schedule:
        type: daily
        time: "22:00"
      zones:
        - zone_id: jardin

    - id: prog_j2
      name: Arrosage J+2
      enabled: false
      schedule:
        type: every_n_days
        n: 2
        start_date: "2026-03-28"
        time: "22:00"
      zones:
        - zone_id: jardin
```

5. Restart HA → check entities appear in Developer Tools → States
6. Verify: 2 switches (`switch.wateringhub_prog_quotidien`, `switch.wateringhub_prog_j2`) + 3 sensors
7. Toggle a switch → verify mutex works (other turns off)
8. Call `wateringhub.stop_all` from Developer Tools → Services
