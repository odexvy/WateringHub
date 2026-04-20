# WateringHub

**Version :** 0.0.27

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/odexvy/WateringHub)](https://github.com/odexvy/WateringHub/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Custom [Home Assistant](https://www.home-assistant.io/) integration for automated watering management.

| Repository | Role |
|------------|------|
| [WateringHub](https://github.com/odexvy/WateringHub) | Backend — this repo (HA custom integration) |
| [WateringHubCard](https://github.com/odexvy/WateringHubCard) | Frontend — HA custom cards (config + display) |

## Introduction

WateringHub lets you manage your irrigation system entirely from the Home Assistant UI. Configure your valves (any HA switch entity), group them into zones, create watering programs with per-valve schedules, and monitor execution in real time. Everything is stored in HA's `.storage` — no YAML needed.

Works with any switch entity: GPIO relays, Zigbee, ESPHome, Shelly, etc.

## Features

- **No YAML** — setup via UI, valves/zones/programs/water supplies via services
- **Water supplies** — assign valves to water supply sources; valves on different supplies run in parallel
- **Per-valve frequency** — each valve runs daily, every N days, or on specific weekdays
- **Real-time tracking** — progress bars, valve sequence with done/running/pending status, multiple active valves
- **Dry run mode** — simulate full execution without commanding physical valves
- **Skip program** — suspend a program for N days without disabling it
- **Strict mutex** — only one program active at a time
- **Persistent state** — survives HA restarts
- **Error handling** — auto-stop + persistent notification on failure

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** > **Custom repositories**
3. Add `https://github.com/odexvy/WateringHub`, category **Integration**
4. Install **WateringHub**
5. Restart Home Assistant
6. Go to **Settings** > **Devices & Services** > **Add Integration** > **WateringHub**

### Manual

Copy `custom_components/wateringhub/` into your HA `custom_components/` directory, restart, then add the integration via the UI.

## Getting started

After adding the integration, configure your valves:

```yaml
service: wateringhub.set_valves
data:
  valves:
    - entity_id: switch.relay_1
      name: Lawn
      zone_id: front_yard
      water_supply_id: main_supply
    - entity_id: switch.relay_2
      name: Flower beds
      zone_id: front_yard
      water_supply_id: main_supply
```

`zone_id` and `water_supply_id` are optional (null or omitted = unassigned).

Then create zones, water supplies, and programs from the [WateringHub Card](https://github.com/odexvy/WateringHubCard) or via services.

## Entities

| Entity | Description |
|--------|-------------|
| `switch.wateringhub_{program_id}` | Toggle program on/off (attributes: schedule, zones, total_duration, dry_run) |
| `sensor.wateringhub_status` | Global status: `idle` / `running` / `error` |
| `sensor.wateringhub_next_run` | Next scheduled run (ISO datetime) |
| `sensor.wateringhub_last_run` | Last run (ISO datetime) |

Switch entities are created/removed dynamically when programs are added/deleted.

### Status sensor attributes

The `sensor.wateringhub_status` sensor exposes additional attributes depending on its state:

**Always available:**
- `available_valves` — list of configured valves (each with optional `zone_id`, `water_supply_id`)
- `zones` — list of zones (name only)
- `water_supplies` — list of water supply sources

**When running:**
- `current_program` — active program ID
- `active_valves` — list of currently open valves (one per water supply, running in parallel)
- `valves_done`, `valves_total`, `progress_percent`
- `dry_run` — `true` if the running program is in dry run mode
- `valves_sequence` — ordered list of today's eligible valves with `status: done/running/pending` and `water_supply_id`

**When error:**
- `current_program`, `error_message`

### Per-valve frequency

Each valve in a program can have its own frequency. Without `frequency`, the valve runs at every trigger (daily).

| Frequency type | Fields | Description |
|----------------|--------|-------------|
| `every_n_days` | `n` (min 2), `start_date` (ISO, optional) | Every N days from start_date |
| `weekdays` | `days` (mon, tue, ..., sun) | Specific days of the week |

The program triggers every day at each scheduled time (one or more). Valves whose frequency doesn't match today are skipped. If no valve is eligible, the program does not start.

## Services

| Service | Description |
|---------|-------------|
| `wateringhub.set_valves` | Replace the entire valve list (entity_id, name, optional zone_id + water_supply_id) |
| `wateringhub.stop_all` | Close all valves immediately, cancel running program |
| `wateringhub.create_zone` | Create a zone (id, name) |
| `wateringhub.update_zone` | Update a zone name |
| `wateringhub.delete_zone` | Delete a zone (clears zone_id on referencing valves) |
| `wateringhub.create_water_supply` | Create a water supply source (id, name) |
| `wateringhub.update_water_supply` | Update a water supply name |
| `wateringhub.delete_water_supply` | Delete a water supply (clears water_supply_id on referencing valves) |
| `wateringhub.create_program` | Create a program (id, name, schedule, zones with durations, dry_run) |
| `wateringhub.update_program` | Update a program (name, schedule, zones, dry_run) |
| `wateringhub.delete_program` | Delete a program and its switch entity |
| `wateringhub.skip_program` | Suspend a program for N days without disabling it (0 to cancel) |

<details>
<summary>Example: create a zone</summary>

```yaml
service: wateringhub.create_zone
data:
  id: jardin
  name: Jardin complet
```

Valve-to-zone assignment is done via `set_valves` (`zone_id` field on each valve).
</details>

<details>
<summary>Example: create a program</summary>

```yaml
service: wateringhub.create_program
data:
  id: prog_quotidien
  name: Arrosage quotidien
  dry_run: false
  schedule:
    times:
      - "06:00"
      - "22:00"
  zones:
    - zone_id: jardin
      valves:
        - valve_id: valve_1
          duration: 15
        - valve_id: valve_2
          duration: 20
          frequency:
            type: every_n_days
            n: 2
            start_date: "2026-04-07"
```
</details>

## Events

All events are fired on `wateringhub_event`:

| Action | Data |
|--------|------|
| `program_started` | `{ program }` |
| `program_finished` | `{ program }` |
| `program_error` | `{ program, error }` |
| `valve_opened` | `{ valve, duration, dry_run, water_supply_id }` |
| `valve_closed` | `{ valve, dry_run }` |

## Development

```bash
pip install -r requirements-dev.txt
ruff check .          # lint
ruff format .         # format
mypy custom_components/
pytest tests/
```

## License

MIT — see [LICENSE](LICENSE).
