# WateringHub — Statut du projet

**Date :** 2026-04-07
**Version :** 0.0.17
**Branche :** master

---

## Architecture

```
.storage/wateringhub (valves + zones + programs JSON)
        |
        v
   __init__.py ---- config flow + service registration
        |
        v
   coordinator.py ---- storage, CRUD, mutex, scheduling, execution
        |
        +--- sensor.py ---- status, next_run, last_run
        +--- switch.py ---- 1 toggle switch per program (dynamic)
```

**Principes :**
- **Valves** = via service `set_valves`, persistance `.storage` (pas de YAML)
- **Config flow** = setup via UI HA (Paramètres > Appareils & Services > Ajouter)
- **Zones + Programs** = CRUD dynamique via services HA, persistance `.storage`
- **Coordinator** = cerveau central (mutex, scheduler, executor)
- **Entities** = switches dynamiques + 3 sensors, listener-driven (pas de polling)

---

## Entités

| Entité                                             | Type   | Description                                                                                                                                      |
| -------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `switch.wateringhub_<program>`                     | Switch | Toggle on/off par programme (attributs : schedule, zones, total_duration, dry_run)                                                               |
| `sensor.wateringhub_status`                        | Sensor | Statut global : `idle` / `running` / `error`                                                                                                    |
| `sensor.wateringhub_status` (attributs permanents) | —      | `available_valves`, `zones`                                                                                                                      |
| `sensor.wateringhub_status` (attributs running)    | —      | `current_program`, `current_zone_name`, `current_valve_name`, `current_valve_start`, `current_valve_duration`, `valves_done`, `valves_total`, `progress_percent`, `valves_sequence`, `dry_run` |
| `sensor.wateringhub_status` (attributs error)      | —      | `current_program`, `error_message`                                                                                                               |
| `sensor.wateringhub_next_run`                      | Sensor | Prochain arrosage prévu (datetime ISO)                                                                                                           |
| `sensor.wateringhub_last_run`                      | Sensor | Dernier arrosage (datetime ISO)                                                                                                                  |

---

## Services (8/8)

| Service                      | Params                             | Description                                              |
| ---------------------------- | ---------------------------------- | -------------------------------------------------------- |
| `wateringhub.set_valves`     | `{ valves: [{ entity_id, name }] }` | Remplacer la liste complète des vannes                   |
| `wateringhub.stop_all`       | `{}`                               | Arrêt immédiat, fermeture de toutes les vannes           |
| `wateringhub.create_zone`    | `{ id, name, valves }`             | Créer une zone (groupement de vannes)                    |
| `wateringhub.update_zone`    | `{ id, name?, valves? }`           | Modifier une zone                                        |
| `wateringhub.delete_zone`    | `{ id }`                           | Supprimer une zone (refuse si utilisée par un programme) |
| `wateringhub.create_program` | `{ id, name, schedule, zones, dry_run? }` | Créer un programme avec schedule et durées par vanne     |
| `wateringhub.update_program` | `{ id, name?, schedule?, zones?, dry_run? }` | Modifier un programme                                    |
| `wateringhub.delete_program` | `{ id }`                           | Supprimer un programme et son switch entity               |

---

## Scheduling

### Schedule programme

Le programme ne définit que l'**heure de déclenchement** : `{ time: "22:00" }`. Il se déclenche tous les jours à cette heure. La fréquence est gérée par vanne.

### Fréquence par vanne

Chaque vanne a sa propre fréquence. Sans `frequency`, la vanne tourne à chaque déclenchement (quotidien).

| Type           | Champs                                | Description                        |
| -------------- | ------------------------------------- | ---------------------------------- |
| (absent)       | —                                     | Tourne à chaque déclenchement      |
| `every_n_days` | `n` (min 2), `start_date` (optionnel) | Tous les N jours depuis start_date |
| `weekdays`     | `days` (mon..sun)                     | Jours spécifiques de la semaine    |

À chaque déclenchement, seules les vannes éligibles sont exécutées. Si aucune vanne n'est éligible, le programme ne démarre pas (reste `idle`).

---

## Execution

- **Mutex strict** — 1 seul programme actif à la fois
- **Séquentiel** — vannes exécutées une par une, zone par zone
- **Tracking temps réel** — vanne courante, progression, timer, `valves_sequence` (liste ordonnée done/running/pending)
- **Annulation** — cancel event vérifié chaque seconde
- **Pause** — 1 seconde entre chaque vanne
- **Error handling** — persistent notification HA + fermeture auto de toutes les vannes
- **Dry run** — mode simulation : séquence complète sans commander les vannes physiques
- **Fréquence par vanne** — override optionnel de la fréquence du programme par vanne (every_n_days, weekdays), vannes non éligibles skippées

---

## Events (bus HA)

Tous les events sont émis sur `wateringhub_event` :

| Action             | Data                          |
| ------------------ | ----------------------------- |
| `program_started`  | `{ program }`                 |
| `program_finished` | `{ program }`                 |
| `program_error`    | `{ program, error }`          |
| `valve_opened`     | `{ valve, duration, dry_run }` |
| `valve_closed`     | `{ valve, dry_run }`           |

---

## Structure du repo

```
WateringHub/
├── custom_components/wateringhub/
│   ├── __init__.py      (204 lignes)  Config entry setup, service registration
│   ├── config_flow.py    (25 lignes)  Config flow (UI setup, single instance)
│   ├── coordinator.py   (798 lignes)  Storage, CRUD, mutex, scheduling, execution
│   ├── sensor.py        (107 lignes)  Status, next_run, last_run sensors
│   ├── switch.py         (98 lignes)  Dynamic program switches
│   ├── const.py          (11 lignes)  Constants (DOMAIN, EVENT_TYPE, PLATFORMS)
│   ├── manifest.json                  HACS metadata (config_flow: true)
│   ├── strings.json                   Config flow UI strings
│   └── services.yaml                  Service schemas + descriptions
├── tests/
│   ├── conftest.py                    Fixtures (mock hass, coordinator)
│   ├── test_coordinator.py            Coordinator unit tests (40+ tests)
│   └── test_validation.py             Config schema tests
├── docs/
│   └── PROJECT_STATUS.md             Statut du projet, roadmap, décisions
├── .github/workflows/ci.yml          CI : ruff + mypy + pytest
├── .pre-commit-config.yaml            Ruff auto-fix
├── requirements-dev.txt               Dev dependencies
├── pyproject.toml
├── hacs.json
├── CLAUDE.md
├── README.md
└── LICENSE
```

**Total** : ~1 250 lignes production, ~400 lignes tests

---

## Outillage

| Outil      | Commande                    | But                              |
| ---------- | --------------------------- | -------------------------------- |
| Lint       | `ruff check .`              | Linting Python                   |
| Format     | `ruff format .`             | Formatage Python                 |
| Types      | `mypy custom_components/`   | Type checking                    |
| Tests      | `pytest tests/`             | 40+ tests unitaires              |
| Pre-commit | Automatique                 | Ruff auto-fix sur les .py stagés |
| CI         | Push/PR sur master          | Ruff + Mypy + Pytest             |

---

## Companion Frontend (repo séparé : WateringHubCard)

- `wateringhub-card` : dashboard (status, programmes, running view, error view)
- `wateringhub-config-card` : gestion (CRUD zones et programmes via services HA)

---

## Bugs connus

| #   | Sévérité | Description                                                                         | Fichier                |
| --- | -------- | ----------------------------------------------------------------------------------- | ---------------------- |
| 1   | Haute    | `remove_listener()` crash si callback absent (ValueError)                           | `coordinator.py:181`   |
| 2   | Haute    | `_notify_listeners()` : si un callback crash, les suivants ne sont pas notifiés     | `coordinator.py:183`   |
| 3   | Haute    | Race condition dans `async_enable_program()` : check `_running_program` sans lock   | `coordinator.py:362`   |
| 4   | Moyenne  | Services handlers sans error handling (exceptions silencieuses)                     | `__init__.py:138-172`  |
| 5   | Basse    | `async_load()` sans protection si `.storage` corrompu                               | `coordinator.py:67`    |

---

## Code clean à faire

| #   | Description                                                                  | Fichier                              |
| --- | ---------------------------------------------------------------------------- | ------------------------------------ |
| 6   | ~~Dead code `flow_sensor`~~ — supprimé avec le YAML config                   | —                                    |
| 7   | Type hints manquants sur `last_run`, `next_run`, `native_value`, callbacks   | `coordinator.py`, `sensor.py`        |
| 8   | `except Exception:` trop large (2 occurrences)                               | `__init__.py:200`, `coordinator.py:408` |
| 9   | `async_run_program()` trop long (~107 lignes), à décomposer                 | `coordinator.py:519-625`             |

---

## Tests manquants

- Exécution réelle de programme (actuellement mock)
- Persistence storage (load/save)
- Race conditions / concurrence
- Service handlers
- Code coverage non tracké en CI

---

## Décisions prises

1. **Valves via service** — les vannes sont gérées via `set_valves`, persistées dans `.storage`. Pas de YAML
2. **Zones + programmes dynamiques** — CRUD via services HA, persistance `.storage/wateringhub`
3. **Mutex strict** — 1 seul programme actif, le switch d'un programme désactive les autres
4. **Listener-driven** — pas de polling, les entities s'abonnent au coordinator
5. **Switches dynamiques** — 1 switch par programme, créé/supprimé sans restart HA
6. **Durées par programme** — les zones sont des groupements logiques, les durées sont par vanne par programme
7. **Pause inter-vannes** — 1 seconde entre chaque vanne (constante `VALVE_PAUSE_SECONDS`)
8. **Cancel event** — vérification chaque seconde pour annulation réactive
9. **Error → auto stop** — en cas d'erreur, fermeture auto de toutes les vannes + persistent notification
10. **Sensors globaux** — status/next_run/last_run sont globaux (pas par programme)
11. **Recalcul next_run chaque minute** — `_async_time_tick` recalcule à chaque tick
12. **`valves_sequence` sur le sensor status** — liste ordonnée de toutes les vannes du programme en cours avec `status: done/running/pending`, construite au lancement et mise à jour dynamiquement via `valves_done`
13. **`dry_run` par programme** — flag boolean persisté, simule l'exécution complète sans commander les vannes physiques, exposé sur switch et sensor status
14. **Schedule = heure uniquement** — le programme ne définit que l'heure de déclenchement (`{ time: "22:00" }`), il se déclenche tous les jours. La fréquence est gérée par vanne, pas par programme (breaking change v0.0.14)
15. **Fréquence par vanne** — `frequency` optionnel sur chaque vanne, types `every_n_days` (n min 2, start_date) et `weekdays` (days). Sans frequency = tourne à chaque déclenchement. Vannes non éligibles exclues de `valves_sequence`. Si aucune vanne éligible, le programme ne démarre pas
16. **`set_valves` service** — remplace la liste complète des vannes, match par `entity_id` pour préserver les IDs existants, persiste dans `.storage`
17. **Pause inter-vannes réduite** — passée de 5s à 1s
18. **Config flow** — setup via UI HA (plus de YAML), `async_setup_entry` / `async_unload_entry`, single instance

---

## Flow de release

```
commit → push → git tag v0.0.X → gh release create
```

HACS : Frontend > Custom repositories > https://github.com/odexvy/WateringHubCard (Plugin)
HACS : Backend > Custom repositories > https://github.com/odexvy/WateringHub (Integration)
Mise à jour : HACS affiche "mise à jour disponible" → installer → redémarrer HA

---

## Roadmap

### Court terme (stabilité)

- [ ] Fix bug #1 — `remove_listener()` crash (`.discard()` au lieu de `.remove()`)
- [ ] Fix bug #2 — `_notify_listeners()` fragile (try/except par callback)
- [ ] Fix bug #3 — race condition `async_enable_program()` (protéger avec `_run_lock`)
- [ ] Fix bug #4 — error handling dans les service handlers
- [ ] Fix bug #5 — protection storage corrompu
- [ ] Code clean #6-9 — dead code, type hints, exceptions, refactoring

### Moyen terme (qualité)

- [ ] Tests exécution réelle de programme
- [ ] Tests persistence storage
- [ ] Tests service handlers
- [ ] Code coverage en CI

### Features (par priorité suggérée)

- [ ] **Run Once** — service `run_program` pour lancer un programme sans l'activer (bouton "Run now")
- [ ] **Rain Delay** — service `rain_delay` + intégration weather entity HA pour skip automatique
- [ ] **Flow Sensor** — lecture du `flow_sensor` pendant l'exécution, calcul consommation (litres)
- [ ] **Historique** — log des exécutions passées, persisté dans `.storage`
- [ ] **Notifications avancées** — début/fin configurable, alerte si pas tourné depuis X jours
- [ ] **Multi-programme** — plusieurs programmes actifs avec scheduler + queue d'exécution
