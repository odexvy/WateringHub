# WateringHub

Custom [Home Assistant](https://www.home-assistant.io/) integration for automated watering management.

> **Requires [WateringHub Card](https://github.com/odexvy/WateringHubCard)** for the dashboard UI. Install it via HACS (Frontend > Plugin).

| Repository | Role |
|------------|------|
| [WateringHub](https://github.com/odexvy/WateringHub) | Backend — this repo (HA custom integration) |
| [WateringHubCard](https://github.com/odexvy/WateringHubCard) | Frontend — HA custom cards -> config and display|

## Features

- Configure valves via `set_valves` service (no YAML, no restart needed)
- Create zones and programs dynamically via services (no restart needed)
- Per-program valve durations with per-valve frequency (every N days, specific weekdays)
- Program schedule = trigger time only, frequency is per valve
- Strict mutex: only one program active at a time
- Sequential valve execution with real-time progress tracking
- Valve sequence with status (`done` / `running` / `pending`) exposed on status sensor
- Dry run mode: simulate full execution without commanding physical valves
- State persisted across restarts (`.storage/wateringhub`)
- Error handling with persistent HA notifications

## Installation (HACS)

1. Open HACS in Home Assistant
2. Go to **Integrations** > **Custom repositories**
3. Add this repository URL, category **Integration**
4. Install **WateringHub**
5. Restart Home Assistant
6. Go to **Settings** > **Devices & Services** > **Add Integration** > **WateringHub**

### Manual

Copy `custom_components/wateringhub/` into your HA `custom_components/` directory, then add the integration via the UI.

## Configuration

No YAML required. Everything is managed via services (from the config card or HA developer tools).

After adding the integration, configure valves via the `set_valves` service:

```yaml
service: wateringhub.set_valves
data:
  valves:
    - entity_id: switch.relay_1
      name: Lawn
    - entity_id: switch.relay_2
      name: Flower beds
```

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
- `available_valves` — list of configured valves
- `zones` — list of configured zones

**When running:**
- `current_program`, `current_zone`, `current_zone_name`
- `current_valve`, `current_valve_name`, `current_valve_start`, `current_valve_duration`
- `valves_done`, `valves_total`, `progress_percent`
- `dry_run` — `true` if the running program is in dry run mode
- `valves_sequence` — ordered list of **today's eligible valves** with `status: done/running/pending` (valves whose frequency doesn't match today are excluded):
  ```json
  [
    {"valve_id": "v1", "valve_name": "Lawn", "zone_id": "z1", "zone_name": "Garden", "duration": 600, "status": "done"},
    {"valve_id": "v2", "valve_name": "Beds", "zone_id": "z1", "zone_name": "Garden", "duration": 900, "status": "running"},
    {"valve_id": "v3", "valve_name": "Veggie", "zone_id": "z2", "zone_name": "Veggie patch", "duration": 1200, "status": "pending"}
  ]
  ```

**When error:**
- `current_program`, `error_message`

### Per-valve frequency

Each valve in a program can have its own frequency. Without `frequency`, the valve runs at every trigger (daily). With `frequency`, it only runs on matching days.

| Frequency type | Fields | Description |
|----------------|--------|-------------|
| `every_n_days` | `n` (min 2), `start_date` (ISO, optional) | Every N days from start_date |
| `weekdays` | `days` (mon, tue, ..., sun) | Specific days of the week |

The program triggers every day at its scheduled time. Valves whose frequency doesn't match today are skipped. If no valve is eligible, the program does not start (stays `idle`).

## Services

| Service | Description |
|---------|-------------|
| `wateringhub.set_valves` | Replace the entire valve list (entity_id + name per valve) |
| `wateringhub.stop_all` | Close all valves immediately, cancel running program |
| `wateringhub.create_zone` | Create a zone (id, name, valve list) |
| `wateringhub.update_zone` | Update a zone |
| `wateringhub.delete_zone` | Delete a zone (fails if used by a program) |
| `wateringhub.create_program` | Create a program (id, name, schedule, zones with durations, dry_run) |
| `wateringhub.update_program` | Update a program (name, schedule, zones, dry_run) |
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
  dry_run: false  # optional, simulate without commanding valves
  schedule:
    time: "22:00"
  zones:
    - zone_id: jardin
      valves:
        - valve_id: valve_1
          duration: 15
        - valve_id: valve_2
          duration: 20
          frequency:  # optional, override schedule frequency for this valve
            type: every_n_days
            n: 2
            start_date: "2026-04-07"
```

## Events

All events are fired on `wateringhub_event`:

| Action | Data |
|--------|------|
| `program_started` | `{ program }` |
| `program_finished` | `{ program }` |
| `program_error` | `{ program, error }` |
| `valve_opened` | `{ valve, duration, dry_run }` |
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
