# Selenium end-to-end tests — event_raffle

`test_event_raffle_selenium.py` drives the raffle wheel against a **running**
Odoo instance (Chromium via Selenium). It is a standalone script — it does not
depend on the repo's `script/selenium` framework.

## What it covers

1. **Tux size** — opens the raffle form and asserts the Tux/wheel height ratio
   (`data-tux-wheel-ratio` on the canvas) stays within **25%–40%**.
2. **Draws + animations** — in fullscreen, runs one draw per Tux animation
   (`peace`, `jump`, `flag`, `dance` — the rotation order), checking a winner is
   shown and the eligible pool shrinks (winner removal).
3. **Persistence** — verifies the `event.raffle.draw` records via XML-RPC.
4. **Winners smart button** — opens the event and checks the "Winners" list.
5. **Mark absent** — marks a winner absent and verifies it stays out of the pool.

A screenshot is saved at each step (see `--screenshot-dir`), including the four
animations, so the wheel/Tux/flag rendering can be inspected visually.

## Requirements

- `selenium` (in `.venv.erplibre`), Chromium + a matching `chromedriver`
  (auto-detected from `~/.wdm` / `~/.cache/selenium`, or pass `--chromedriver`).
- The `event_raffle` module installed on the target database.

## Run

```bash
# 1. start Odoo with the module installed
./odoo_bin.sh db --drop --database test_event_raffle
./run.sh -d test_event_raffle --db-filter test_event_raffle \
    --stop-after-init -i event_raffle
./run.sh -d test_event_raffle --db-filter test_event_raffle \
    --http-port 8069 --workers 0 &

# 2. run the scenarios (headless)
.venv.erplibre/bin/python \
    odoo18.0/addons/addons/event_raffle/selenium/test_event_raffle_selenium.py \
    --url http://localhost:8069 --db test_event_raffle \
    --login admin --password admin --headless
```

Exit code `0` = all scenarios passed, `1` = at least one failed (details printed).

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--url` | `http://localhost:8069` | Odoo base URL |
| `--db` | `test_event_raffle` | Target database |
| `--login` / `--password` | `admin` / `admin` | Credentials |
| `--headless` | off | Run Chromium without a window |
| `--chromium` | `/usr/bin/chromium` | Browser binary |
| `--chromedriver` | auto | chromedriver path |
| `--window` | `1400,900` | Browser window size |
| `--screenshot-dir` | `selenium/screenshots` | Where screenshots go (gitignored) |

> Headless WebGL uses SwiftShader (`--enable-unsafe-swiftshader`,
> `--use-gl=angle --use-angle=swiftshader`) so the three.js canvas renders
> without a GPU.
