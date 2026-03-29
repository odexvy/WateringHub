# WateringHub

Custom Home Assistant component for automated watering management, installable via [HACS](https://hacs.xyz/).

> **Requires:** [WateringHub Card](https://github.com/odexvy/WateringHubCard) — companion Lovelace card for the dashboard UI (install via HACS as a Frontend plugin)

## Features

- Configure physical valves (HA switch entities) in YAML
- Create zones and programs dynamically via services (no restart needed)
- Flexible schedules: daily, every N days, specific weekdays
- Per-program valve durations
- Strict mutex: only one program active at a time
- Sequential valve execution with real-time progress tracking
- State persisted across restarts (`.storage/wateringhub`)
- Error handling with persistent HA notifications

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations** > **+** > **Custom repositories**
2. Add this repository URL, category: **Integration**
3. Install **WateringHub**
4. Also install [WateringHub Card](https://github.com/odexvy/WateringHubCard) (category: **Plugin**)
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

| Entity | Type | Description |
|--------|------|-------------|
| `switch.wateringhub_<program_id>` | Switch | Toggle a program on/off (mutex) |
| `sensor.wateringhub_status` | Sensor | `idle` / `running` / `error` |
| `sensor.wateringhub_next_run` | Sensor | Next scheduled run datetime |
| `sensor.wateringhub_last_run` | Sensor | Last completed run datetime |

Switch entities are created/removed dynamically when programs are added/deleted.

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

### Example: create a zone via service

```yaml
service: wateringhub.create_zone
data:
  id: jardin
  name: Jardin complet
  valves:
    - valve_1
    - valve_2
```

### Example: create a program via service

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

## License

MIT - see [LICENSE](LICENSE).
