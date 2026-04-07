# WateringHub

Custom [Home Assistant](https://www.home-assistant.io/) integration for automated watering management.

> **Requires [WateringHub Card](https://github.com/odexvy/WateringHubCard)** for the dashboard UI. Install it via HACS (Frontend > Plugin).

| Repository | Role |
|------------|------|
| [WateringHub](https://github.com/odexvy/WateringHub) | Backend — this repo (HA custom integration) |
| [WateringHubCard](https://github.com/odexvy/WateringHubCard) | Frontend — HA custom card |

## Features

- Configure physical valves (HA switch entities) in YAML
- Create zones and programs dynamically via services (no restart needed)
- Flexible schedules: daily, every N days, specific weekdays
- Per-program valve durations
- Strict mutex: only one program active at a time
- Sequential valve execution with real-time progress tracking
- Valve sequence with status (`done` / `running` / `pending`) exposed on status sensor
- State persisted across restarts (`.storage/wateringhub`)
- Error handling with persistent HA notifications

## Installation (HACS)

1. Open HACS in Home Assistant
2. Go to **Integrations** > **Custom repositories**
3. Add this repository URL, category **Integration**
4. Install **WateringHub**
5. Restart Home Assistant

### Manual

Copy `custom_components/wateringhub/` into your HA `custom_components/` directory.

## Configuration

Only valves are defined in `configuration.yaml` (your physical devices). Zones and programs are managed dynamically via the card or HA services.

```yaml
wateringhub:
  valves:
    - id: valve_1
      name: My First Valve
      entity_id: switch.your_valve_1
      flow_sensor: sensor.your_valve_1_flow  # optional
    - id: valve_2
      name: My Second Valve
      entity_id: switch.your_valve_2
```

## Entities

| Entity | Description |
|--------|-------------|
| `switch.wateringhub_{program_id}` | Toggle program on/off (attributes: schedule, zones, total_duration) |
| `sensor.wateringhub_status` | Global status: `idle` / `running` / `error` |
| `sensor.wateringhub_next_run` | Next scheduled run (ISO datetime) |
| `sensor.wateringhub_last_run` | Last run (ISO datetime) |

Switch entities are created/removed dynamically when programs are added/deleted.

### Status sensor attributes

The `sensor.wateringhub_status` sensor exposes additional attributes depending on its state:

**Always available:**
- `available_valves` — list of configured valves
- `zones` — list of configured zones

**When running:**
- `current_program`, `current_zone`, `current_zone_name`
- `current_valve`, `current_valve_name`, `current_valve_start`, `current_valve_duration`
- `valves_done`, `valves_total`, `progress_percent`
- `valves_sequence` — ordered list of all valves in the program with `status: done/running/pending`:
  ```json
  [
    {"valve_id": "v1", "valve_name": "Lawn", "zone_id": "z1", "zone_name": "Garden", "duration": 600, "status": "done"},
    {"valve_id": "v2", "valve_name": "Beds", "zone_id": "z1", "zone_name": "Garden", "duration": 900, "status": "running"},
    {"valve_id": "v3", "valve_name": "Veggie", "zone_id": "z2", "zone_name": "Veggie patch", "duration": 1200, "status": "pending"}
  ]
  ```

**When error:**
- `current_program`, `error_message`

## Services

| Service | Description |
|---------|-------------|
| `wateringhub.stop_all` | Close all valves immediately, cancel running program |
| `wateringhub.create_zone` | Create a zone (id, name, valve list) |
| `wateringhub.update_zone` | Update a zone |
| `wateringhub.delete_zone` | Delete a zone (fails if used by a program) |
| `wateringhub.create_program` | Create a program (id, name, schedule, zones with durations) |
| `wateringhub.update_program` | Update a program |
| `wateringhub.delete_program` | Delete a program and its switch entity |

### Example: create a zone

```yaml
service: wateringhub.create_zone
data:
  id: jardin
  name: Jardin complet
  valves:
    - valve_1
    - valve_2
```

### Example: create a program

```yaml
service: wateringhub.create_program
data:
  id: prog_quotidien
  name: Arrosage quotidien
  schedule:
    type: daily
    time: "22:00"
  zones:
    - zone_id: jardin
      valves:
        - valve_id: valve_1
          duration: 15
        - valve_id: valve_2
          duration: 20
```

## Events

All events are fired on `wateringhub_event`:

| Action | Data |
|--------|------|
| `program_started` | `{ program }` |
| `program_finished` | `{ program }` |
| `program_error` | `{ program, error }` |
| `valve_opened` | `{ valve, duration }` |
| `valve_closed` | `{ valve }` |

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
