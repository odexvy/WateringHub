# WateringHub — CLAUDE.md

## Git Policy

Claude has **read-only** access to git (status, log, diff, blame, etc.).
Only the developer can run git write commands (add, commit, push, tag, etc.).
Never attempt to commit, push, or create tags — ask the developer to do it.

## Project

Custom Home Assistant component (HACS) for automated watering management.
Domain: `wateringhub`.

- **Backend** : https://github.com/odexvy/WateringHub
- **Frontend** : https://github.com/odexvy/WateringHubCard

## Architecture

- **Valves** = YAML only (`configuration.yaml`), physical hardware config
- **Zones + Programs** = managed via HA services, persisted in `.storage/wateringhub`
- **Coordinator** = central logic (mutex, scheduling, execution, CRUD, storage)
- **Switches** = 1 per program, created/removed dynamically
- **Sensors** = status (with execution tracking + available_valves + zones), next_run, last_run
- **Two Lovelace cards** in separate repo (WateringHubCard):
  - `wateringhub-card` = dashboard (status, programs, execution progress)
  - `wateringhub-config-card` = management (CRUD zones/programs)

## Code Standards

- Python 3.11+, HA 2024.1+
- No external Python dependencies
- Ruff (lint + format) via pre-commit and CI
- Mypy for type checking (CI only)
- Pytest for unit tests (CI only)
- MIT license — every Python source file must include:
  ```python
  # SPDX-License-Identifier: MIT
  # Copyright (c) 2026 WateringHub contributors
  ```

## Key Files

- `custom_components/wateringhub/__init__.py` — setup, YAML validation, service registration
- `custom_components/wateringhub/coordinator.py` — storage, CRUD, mutex, scheduling, execution
- `custom_components/wateringhub/switch.py` — dynamic program switch entities
- `custom_components/wateringhub/sensor.py` — status, next_run, last_run sensors
- `custom_components/wateringhub/const.py` — constants
- `custom_components/wateringhub/services.yaml` — service schemas
