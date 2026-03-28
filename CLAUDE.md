# WateringHub — CLAUDE.md

## Git Policy

Claude has **read-only** access to git (status, log, diff, blame, etc.).
Only the developer can run git write commands (add, commit, push, tag, etc.).
Never attempt to commit, push, or create tags — ask the developer to do it.

## Project

Custom Home Assistant component (HACS) for automated watering management.
Domain: `wateringhub`. Repo: `WateringHub`.

## Code Standards

- Python 3.11+, HA 2024.1+
- No external Python dependencies
- MIT license — every Python source file must include:
  ```python
  # SPDX-License-Identifier: MIT
  # Copyright (c) 2026 WateringHub contributors
  ```
- Must pass `hassfest` validation
