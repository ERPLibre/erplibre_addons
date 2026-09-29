# Selenium end-to-end tests — erplibre_event_table

`test_erplibre_event_table_selenium.py` drives the rotating tables floor plan
against a **running** Odoo instance (Chromium via Selenium). It is a standalone
script — it does not depend on the repo's `script/selenium` framework, and Odoo
never runs it: the test loader only reads `tests/`.

## What it covers

1. **Floor plan drawn** — opens the plan form and waits until the four table
   blocks are on screen.
2. **Round 1 seating** — every participant carries a badge, and the badges
   match the `event.table.assignment` rows read over XML-RPC.
3. **Round switch** — round 2 shows another seating, again matching the rows.
4. **Table move** — turns on *Edit Layout*, drags one table, and checks that
   exactly one `event.table` changed `position_h`/`position_v` in the database.
5. **Swap** — drops one person's badge onto another's and checks the two
   assignments exchanged tables.
6. **Contact smart button** — opens a contact and checks the assignment list
   holds one row per round.

A screenshot is saved at each step (see `--screenshot-dir`).

## Requirements

- `selenium` (in `.venv.erplibre`), Chromium + a matching `chromedriver`
  (auto-detected from `~/.wdm` / `~/.cache/selenium`, or pass `--chromedriver`).
- The `erplibre_event_table` module installed on the target database.

## Run

```bash
# 1. start Odoo with the module installed
./odoo_bin.sh db --drop --database test_erplibre_event_table
./run.sh -d test_erplibre_event_table --db-filter test_erplibre_event_table \
    --stop-after-init -i erplibre_event_table
./run.sh -d test_erplibre_event_table --db-filter test_erplibre_event_table \
    --http-port 18069 --workers 0 &

# 2. run the scenarios (headless)
.venv.erplibre/bin/python \
    odoo18.0/addons/ERPLibre_erplibre_addons/erplibre_event_table/selenium/test_erplibre_event_table_selenium.py \
    --url http://localhost:18069 --db test_erplibre_event_table \
    --login admin --password admin --headless
```

Exit code `0` = all scenarios passed, `1` = at least one failed (details
printed).

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--url` | `http://localhost:8069` | Odoo base URL |
| `--db` | `test_erplibre_event_table` | Target database |
| `--login` / `--password` | `admin` / `admin` | Credentials |
| `--headless` | off | Run Chromium without a window |
| `--chromium` | `/usr/bin/chromium` | Browser binary |
| `--chromedriver` | auto | chromedriver path |
| `--window` | `1400,900` | Browser window size |
| `--screenshot-dir` | `selenium/screenshots` | Where screenshots go (gitignored) |

> The drag steps move the pointer in several hops: the core's draggable hook
> arms only past a few pixels of tolerance, so a single-jump drag drops
> nothing.
