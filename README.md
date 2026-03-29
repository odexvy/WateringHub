# WateringHub

Custom Home Assistant component for automated watering management, installable via [HACS](https://hacs.xyz/).

> **Requires:** [WateringHub Card](https://github.com/odexvy/WateringHubCard) — companion Lovelace card for the dashboard UI (install via HACS as a Frontend plugin)

## Features

- Configure physical valves (HA switch entities)
- Group valves into zones with per-valve durations
- Create watering programs with flexible schedules (daily, every N days, specific weekdays)
- Strict mutex: only one program active at a time
- Sequential valve execution with automatic open/close
- `stop_all` service to immediately close all valves

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

Add to your `configuration.yaml`:

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

  zones:
    - id: jardin
      name: Jardin complet
      valves:
        - valve_1
        - valve_2

  programs:
    - id: prog_quotidien
      name: Arrosage quotidien
      enabled: true
      schedule:
        type: daily          # daily | every_n_days | weekdays
        time: "22:00"
      zones:
        - zone_id: jardin
          valves:
            - valve_id: valve_1
              duration: 15   # minutes
            - valve_id: valve_2
              duration: 20

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
          valves:
            - valve_id: valve_1
              duration: 10
            - valve_id: valve_2
              duration: 10
```

### Schedule types

| Type | Fields | Description |
|------|--------|-------------|
| `daily` | `time` | Every day at the specified time |
| `every_n_days` | `time`, `n`, `start_date` | Every N days from the start date |
| `weekdays` | `time`, `days` | On specific days (`["mon", "wed", "fri"]`) |

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| `switch.wateringhub_<program_id>` | Switch | Toggle a program on/off (mutex) |
| `sensor.wateringhub_status` | Sensor | `idle` / `running` / `error` |
| `sensor.wateringhub_next_run` | Sensor | Next scheduled run datetime |
| `sensor.wateringhub_last_run` | Sensor | Last completed run datetime |

## Services

| Service | Description |
|---------|-------------|
| `wateringhub.stop_all` | Close all valves immediately, cancel running program |

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
