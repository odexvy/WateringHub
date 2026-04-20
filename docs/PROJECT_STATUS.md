# WateringHub — Statut du projet

**Date :** 2026-04-13
**Version :** 0.0.27
**Branche :** master

---

## Architecture

```
.storage/wateringhub (valves + zones + water_supplies + programs JSON)
        |
        v
   __init__.py ---- config flow + service registration
        |
        v
   coordinator.py ---- storage, CRUD, mutex, scheduling, parallel execution
        |
        +--- sensor.py ---- status, next_run, last_run
        +--- switch.py ---- 1 toggle switch per program (dynamic)
```

**Principes :**
- **Valves** = via service `set_valves`, chaque vanne porte `zone_id` + `water_supply_id` (optionnels)
- **Zones** = CRUD de noms uniquement, l'assignation vanne→zone est sur la vanne
- **Water Supplies** = CRUD de noms uniquement, l'assignation vanne→arrivée est sur la vanne
- **Config flow** = setup via UI HA (Paramètres > Appareils & Services > Ajouter)
- **Programs** = CRUD dynamique via services HA, persistance `.storage`
- **Execution** = vannes groupées par arrivée d'eau, pipelines parallèles (1 vanne active par arrivée)
- **Coordinator** = cerveau central (mutex, scheduler, executor parallèle)
- **Entities** = switches dynamiques + 3 sensors, listener-driven (pas de polling)

---

## Entités

| Entité                                             | Type   | Description                                                                                                                                      |
| -------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `switch.wateringhub_<program>`                     | Switch | Toggle on/off par programme (attributs : schedule, zones, total_duration, dry_run, skip_until)                                                   |
| `sensor.wateringhub_status`                        | Sensor | Statut global : `idle` / `running` / `error`                                                                                                    |
| `sensor.wateringhub_status` (attributs permanents) | —      | `available_valves` (avec zone_id, water_supply_id), `zones`, `water_supplies`                                                                    |
| `sensor.wateringhub_status` (attributs running)    | —      | `current_program`, `active_valves` (N vannes en parallèle), `valves_done`, `valves_total`, `progress_percent`, `valves_sequence` (avec status + water_supply_id), `dry_run` |
| `sensor.wateringhub_status` (attributs error)      | —      | `current_program`, `error_message`                                                                                                               |
| `sensor.wateringhub_next_run`                      | Sensor | Prochain arrosage prévu (datetime ISO)                                                                                                           |
| `sensor.wateringhub_last_run`                      | Sensor | Dernier arrosage (datetime ISO)                                                                                                                  |

---

## Services (12/12)

| Service                          | Params                                                          | Description                                                      |
| -------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------- |
| `wateringhub.set_valves`         | `{ valves: [{ entity_id, name, water_supply_id, zone_id }] }` | Remplacer la liste complète des vannes                           |
| `wateringhub.stop_all`           | `{}`                                                            | Arrêt immédiat, fermeture de toutes les vannes                   |
| `wateringhub.create_zone`        | `{ id, name }`                                                  | Créer une zone (nom uniquement)                                  |
| `wateringhub.update_zone`        | `{ id, name? }`                                                 | Modifier le nom d'une zone                                       |
| `wateringhub.delete_zone`        | `{ id }`                                                        | Supprimer une zone (zone_id des vannes passe à null)             |
| `wateringhub.create_water_supply`| `{ id, name }`                                                  | Créer une arrivée d'eau                                          |
| `wateringhub.update_water_supply`| `{ id, name? }`                                                 | Modifier le nom d'une arrivée d'eau                              |
| `wateringhub.delete_water_supply`| `{ id }`                                                        | Supprimer une arrivée (water_supply_id des vannes passe à null)  |
| `wateringhub.create_program`     | `{ id, name, schedule, zones, dry_run? }`                       | Créer un programme avec schedule et durées par vanne             |
| `wateringhub.update_program`     | `{ id, name?, schedule?, zones?, dry_run? }`                    | Modifier un programme                                            |
| `wateringhub.delete_program`     | `{ id }`                                                        | Supprimer un programme et son switch entity                      |
| `wateringhub.skip_program`       | `{ id, days }`                                                  | Suspendre un programme N jours (0 pour annuler)                  |

---

## Scheduling

### Schedule programme

Le programme définit une ou plusieurs **heures de déclenchement** : `{ times: ["22:00"] }` ou `{ times: ["06:00", "22:00"] }`. Il se déclenche tous les jours à chacune de ces heures. La fréquence est gérée par vanne.

### Fréquence par vanne

Chaque vanne a sa propre fréquence. Sans `frequency`, la vanne tourne à chaque déclenchement (quotidien).

| Type           | Champs                                | Description                        |
| -------------- | ------------------------------------- | ---------------------------------- |
| (absent)       | —                                     | Tourne à chaque déclenchement      |
| `every_n_days` | `n` (min 2), `start_date` (optionnel) | Tous les N jours depuis start_date |
| `weekdays`     | `days` (mon..sun)                     | Jours spécifiques de la semaine    |

À chaque déclenchement, seules les vannes éligibles sont exécutées. Si aucune vanne n'est éligible, le programme ne démarre pas (reste `idle`).

### Skip program

`skip_program { id, days }` suspend un programme sans le désactiver (switch reste ON). `skip_until` est exposé comme attribut du switch. `days: 0` annule le skip. Le skip expire automatiquement.

---

## Execution

- **Mutex strict** — 1 seul programme actif à la fois
- **Parallèle par arrivée** — vannes groupées par `water_supply_id`, chaque arrivée est un pipeline séquentiel, les pipelines tournent en parallèle (`asyncio.gather`)
- **`active_valves`** — liste des vannes actuellement ouvertes (1 par arrivée active)
- **Tracking temps réel** — `valves_sequence` avec status done/running/pending par entrée
- **`total_duration`** — max(somme par arrivée), pas la somme brute (parallélisme)
- **Annulation** — cancel event vérifié chaque seconde, propage à tous les pipelines
- **Pause** — 1 seconde entre chaque vanne (au sein d'un même pipeline)
- **Error handling** — persistent notification HA + fermeture auto de toutes les vannes
- **Dry run** — mode simulation : séquence complète sans commander les vannes physiques
- **Fréquence par vanne** — vannes non éligibles exclues de la séquence

---

## Events (bus HA)

Tous les events sont émis sur `wateringhub_event` :

| Action             | Data                                           |
| ------------------ | ---------------------------------------------- |
| `program_started`  | `{ program }`                                  |
| `program_finished` | `{ program }`                                  |
| `program_error`    | `{ program, error }`                           |
| `valve_opened`     | `{ valve, duration, dry_run, water_supply_id }` |
| `valve_closed`     | `{ valve, dry_run }`                            |

---

## Structure du repo

```
WateringHub/
├── custom_components/wateringhub/
│   ├── __init__.py       Config entry setup, service registration
│   ├── config_flow.py    Config flow (UI setup, single instance)
│   ├── coordinator.py    Storage, CRUD, mutex, scheduling, parallel execution
│   ├── sensor.py         Status, next_run, last_run sensors
│   ├── switch.py         Dynamic program switches
│   ├── const.py          Constants (DOMAIN, EVENT_TYPE, PLATFORMS)
│   ├── manifest.json     HACS metadata (config_flow: true)
│   ├── strings.json      Config flow UI strings
│   └── services.yaml     Service schemas + descriptions
├── tests/
│   ├── conftest.py       Fixtures (mock hass, coordinator)
│   ├── test_coordinator.py  Coordinator unit tests
│   └── test_validation.py   Config schema tests
├── .github/workflows/ci.yml  CI : ruff + mypy + pytest
├── .pre-commit-config.yaml   Ruff auto-fix
├── requirements-dev.txt      Dev dependencies
├── pyproject.toml
├── hacs.json
├── CLAUDE.md
├── README.md
└── LICENSE
```

---

## Outillage

| Outil      | Commande                    | But                              |
| ---------- | --------------------------- | -------------------------------- |
| Lint       | `ruff check .`              | Linting Python                   |
| Format     | `ruff format .`             | Formatage Python                 |
| Types      | `mypy custom_components/`   | Type checking                    |
| Tests      | `pytest tests/`             | Tests unitaires                  |
| Pre-commit | Automatique                 | Ruff auto-fix sur les .py stagés |
| CI         | Push/PR sur master          | Ruff + Mypy + Pytest             |

---

## Companion Frontend (repo séparé : WateringHubCard)

- `wateringhub-card` : dashboard (status, programmes, running view avec vannes parallèles, error view)
- `wateringhub-config-card` : gestion (CRUD zones, arrivées d'eau, vannes avec assignation zone+arrivée, programmes)

---

## Décisions prises

1. **Valves via service** — les vannes sont gérées via `set_valves`, persistées dans `.storage`. Pas de YAML
2. **Zones = noms uniquement** — l'assignation vanne→zone est sur la vanne (`zone_id`), pas sur la zone
3. **Water supplies = noms uniquement** — l'assignation vanne→arrivée est sur la vanne (`water_supply_id`)
4. **Mutex strict** — 1 seul programme actif, le switch d'un programme désactive les autres
5. **Listener-driven** — pas de polling, les entities s'abonnent au coordinator
6. **Switches dynamiques** — 1 switch par programme, créé/supprimé sans restart HA
7. **Durées par programme** — les zones sont des groupements logiques, les durées sont par vanne par programme
8. **Exécution parallèle par arrivée** — vannes groupées par `water_supply_id`, pipelines concurrents via `asyncio.gather`
9. **Pause inter-vannes** — 1 seconde entre chaque vanne au sein d'un pipeline (constante `VALVE_PAUSE_SECONDS`)
10. **Cancel event** — vérification chaque seconde pour annulation réactive, propagé à tous les pipelines
11. **Error → auto stop** — en cas d'erreur, fermeture auto de toutes les vannes + persistent notification
12. **Sensors globaux** — status/next_run/last_run sont globaux (pas par programme)
13. **Recalcul next_run chaque minute** — `_async_time_tick` recalcule à chaque tick
14. **`active_valves` sur le sensor status** — liste des vannes actuellement ouvertes (remplace l'ancien `current_valve` unique)
15. **`valves_sequence` sur le sensor status** — liste ordonnée avec `status: done/running/pending` et `water_supply_id`
16. **`dry_run` par programme** — flag boolean persisté, simule l'exécution complète sans commander les vannes physiques
17. **Schedule = liste d'heures** — le programme définit une ou plusieurs heures de déclenchement (`times: [...]`), fréquence gérée par vanne
18. **Fréquence par vanne** — `frequency` optionnel, types `every_n_days` et `weekdays`. Sans frequency = quotidien
19. **`set_valves` centralise les assignations** — chaque vanne porte `zone_id` + `water_supply_id` (optionnels, null = non assigné)
20. **Delete zone/water_supply = clear refs** — suppression nettoie les références sur les vannes au lieu de refuser
21. **Skip program** — suspension temporaire sans désactiver, auto-clear à l'expiration
22. **Config flow** — setup via UI HA, single instance
23. **`total_duration` = max par arrivée** — durée parallèle, pas la somme brute

---

## Flow de release

```
commit → push → git tag v0.0.X → gh release create
```

HACS : Frontend > Custom repositories > https://github.com/odexvy/WateringHubCard (Plugin)
HACS : Backend > Custom repositories > https://github.com/odexvy/WateringHub (Integration)
Mise à jour : HACS affiche "mise à jour disponible" → installer → redémarrer HA

---

## Bugs connus

| #   | Sévérité | Description                                                                         |
| --- | -------- | ----------------------------------------------------------------------------------- |
| 1   | Haute    | `remove_listener()` crash si callback absent (ValueError)                           |
| 2   | Haute    | `_notify_listeners()` : si un callback crash, les suivants ne sont pas notifiés     |
| 3   | Haute    | Race condition dans `async_enable_program()` : check `_running_program` sans lock   |
| 4   | Moyenne  | Services handlers sans error handling (exceptions silencieuses)                     |
| 5   | Basse    | `async_load()` sans protection si `.storage` corrompu                               |

---

## Tests manquants

- Exécution réelle de programme (actuellement mock)
- Exécution parallèle multi-pipeline end-to-end
- Persistence storage (load/save)
- Race conditions / concurrence
- Service handlers
- Code coverage non tracké en CI

---

## Roadmap

### Court terme (stabilité)

- [ ] Fix bug #1 — `remove_listener()` crash
- [ ] Fix bug #2 — `_notify_listeners()` fragile
- [ ] Fix bug #3 — race condition `async_enable_program()`
- [ ] Fix bug #4 — error handling dans les service handlers
- [ ] Fix bug #5 — protection storage corrompu

### Features (par priorité suggérée)

- [ ] **Run Once** — service `run_program` pour lancer un programme sans l'activer
- [ ] **Rain Delay** — intégration weather entity HA pour skip automatique
- [ ] **Flow Sensor** — lecture du débit pendant l'exécution, calcul consommation
- [ ] **Historique** — log des exécutions passées
- [ ] **Multi-programme** — plusieurs programmes actifs avec scheduler + queue d'exécution
