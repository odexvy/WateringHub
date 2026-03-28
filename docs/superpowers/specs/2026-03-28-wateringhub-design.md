# WateringHub — Design Spec

## Overview

Custom Home Assistant component (HACS) for automated watering management.
Domain: `wateringhub`. Repo: `WateringHub`.

Users configure valves (physical switches), group them into zones, and create programs (schedules) that run zones sequentially. Only one program can be active at a time (strict mutex).

## Data Model

### Valve
```
id: string
name: string
entity_id: string          # HA switch entity (e.g. switch.0xe406bffffed0fdc0)
flow_sensor: string|null   # optional flow sensor entity
```

### Zone
```
id: string
name: string
valves: [{ valve_id: string, duration: number }]  # duration in minutes
```

### Program
```
id: string
name: string
enabled: boolean
schedule:
  type: "daily" | "every_n_days" | "weekdays"
  time: "HH:MM"
  n?: number              # for every_n_days
  days?: string[]         # for weekdays ["mon", "wed", "fri"]
  start_date?: string     # for every_n_days, ISO reference date
zones: [{ zone_id: string }]
```

## Architecture

Approach A — monolithic Coordinator. Single `WateringHubCoordinator` class handles config parsing, mutex, scheduling, and execution.

```
configuration.yaml
       │
       ▼
__init__.py ─── parse config ─── WateringHubCoordinator
       │                              │
       │                    ┌─────────┼─────────┐
       │                    │         │         │
       │                 mutex    scheduler  executor
       │                          (async_    (sequential
       │                          track_     valve
       │                          time)      control)
       ▼
 Platforms
 ├── switch.py  →  ProgramSwitch (1 per program)
 └── sensor.py  →  NextRunSensor, LastRunSensor, StatusSensor
```

### File Structure
```
custom_components/
└── wateringhub/
    ├── __init__.py        # setup, unload, register services
    ├── manifest.json
    ├── const.py           # DOMAIN, EVENT_TYPE, etc.
    ├── coordinator.py     # central logic: scheduling, execution, mutex
    ├── switch.py          # ProgramSwitch entity (toggle on/off)
    ├── sensor.py          # next_run, last_run, status sensors
    ├── services.yaml
    └── translations/
        └── en.json
```

Root files: `hacs.json`, `LICENSE` (MIT).

## Coordinator Detail

### Mutex
- Dict of programs with `enabled: bool`.
- Enabling a program disables all others.
- If a program is running and another is enabled → `stop_all()` then start new one.

### Scheduling
- Uses `async_track_time_change` (HA helper) to check every minute.
- Evaluates if the active program should run now based on schedule type:
  - `daily`: every day at configured time
  - `every_n_days`: every N days from `start_date` at configured time
  - `weekdays`: on specified days at configured time

### Executor
- `async_run_program(program_id)`:
  1. Fire `program_started` event
  2. For each zone in order → for each valve in order:
     - `switch.turn_on` → wait `duration` → `switch.turn_off` → 5s pause
  3. Fire `program_finished` event
- Cancellation via `asyncio.Event` (like JS `AbortController`)
- On error: `stop_all()` + fire `program_error` event

## Entities

### Switches (1 per program)
| YAML program | HA entity | Display name |
|---|---|---|
| `prog_quotidien` | `switch.wateringhub_prog_quotidien` | Arrosage quotidien |
| `prog_j2` | `switch.wateringhub_prog_j2` | Arrosage J+2 |

**ON**: enables the program, disables all others (mutex), scheduler recalculates next_run.
**OFF**: disables the program. If running, stops execution and closes all valves.

Switches observe the Coordinator and call `async_write_ha_state()` on state changes.

### Sensors (3 global)
| Sensor | Value | Updates when |
|---|---|---|
| `sensor.wateringhub_status` | `idle` / `running` / `error` | Program starts/stops/errors |
| `sensor.wateringhub_next_run` | datetime of next scheduled run | Program enabled/disabled, schedule changes |
| `sensor.wateringhub_last_run` | datetime of last completed run | Program finishes |

### Services
| Service | Description |
|---|---|
| `wateringhub.stop_all` | Close all valves immediately, cancel running execution |

### Events
All fired on `wateringhub_event` bus with `action` field:
- `program_started` — `{ action, program }`
- `program_finished` — `{ action, program }`
- `program_error` — `{ action, program, error }`
- `valve_opened` — `{ action, valve, duration }`
- `valve_closed` — `{ action, valve }`

## Error Handling

When a valve fails to respond (device offline, service call error):
1. Abort the entire program execution
2. Close all currently open valves via `stop_all()`
3. Fire `program_error` event with error details
4. Set status sensor to `error`

## Constraints

- HA 2024.1+, Python 3.11+
- No external Python dependencies
- Must pass `hassfest` validation
- All entities cleaned up on `async_unload_entry` / platform unload
- MIT license with SPDX header on all Python files

## Testing Workflow

Code → commit → push → GitHub pre-release tag → HACS update → restart HA.
Release naming: `v0.0.x-alpha` → `v0.1.0-beta` → `v1.0.0`.
