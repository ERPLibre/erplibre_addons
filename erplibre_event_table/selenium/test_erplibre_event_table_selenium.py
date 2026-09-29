#!/usr/bin/env python3
# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""End-to-end Selenium scenarios for the ``erplibre_event_table`` module.

Runs against a *live* Odoo instance (the module must be installed on the
target database). Data is created through the external XML-RPC API: an
event with rotating tables, a plan of 4 tables of 4 seats and 14 people.
The floor plan is then driven through the web UI: switching rounds,
moving a table and checking its stored position, swapping two people and
checking their assignments, and opening the contact's smart button.

Screenshots are written to ``--screenshot-dir`` for visual inspection.

Example::

    ./run.sh -d test_erplibre_event_table \\
        --db-filter test_erplibre_event_table --http-port 8069 --workers 0 &
    .venv.erplibre/bin/python \\
        odoo18.0/addons/ERPLibre_erplibre_addons/erplibre_event_table/selenium/test_erplibre_event_table_selenium.py \\
        --url http://localhost:8069 --db test_erplibre_event_table \\
        --login admin --password admin --headless
"""
import argparse
import os
import sys
import time
import xmlrpc.client

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

TABLE_COUNT = 4
SEATS_PER_TABLE = 4
PARTICIPANT_COUNT = 14
ROUND_COUNT = 3


# --------------------------------------------------------------------------- #
# XML-RPC data setup
# --------------------------------------------------------------------------- #
class Rpc:
    def __init__(self, url, db, user, password):
        self.db = db
        self.password = password
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            raise RuntimeError("XML-RPC authentication failed")
        self.models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def exe(self, model, method, *params, **kw):
        return self.models.execute_kw(
            self.db,
            self.uid,
            self.password,
            model,
            method,
            list(params),
            kw,
        )


def setup_data(rpc):
    """Create an event, its contacts and a chosen plan; return useful ids.

    Seats 14 people at 4 tables of 4: two seats stay free, so a move onto a
    free seat and a swap with a full table are both reachable.
    """
    event_id = rpc.exe(
        "event.event",
        "create",
        [
            {
                "name": "Selenium Rotating Tables",
                "date_begin": "2026-09-01 09:00:00",
                "date_end": "2026-09-01 18:00:00",
                "use_rotating_tables": True,
            }
        ],
    )[0]
    partner_ids = []
    for index in range(PARTICIPANT_COUNT):
        partner_ids.append(
            rpc.exe(
                "res.partner",
                "create",
                [
                    {
                        "name": f"Selenium Guest {index + 1:02d}",
                        "email": f"guest{index + 1:02d}@example.com",
                    }
                ],
            )[0]
        )

    wizard_id = rpc.exe(
        "event.table.participant.wizard",
        "create",
        [
            {
                "event_id": event_id,
                "registration_scope": "none",
                "partner_ids": [(6, 0, partner_ids)],
            }
        ],
    )[0]
    rpc.exe("event.table.participant.wizard", "action_add", [wizard_id])
    plan_id = rpc.exe(
        "event.table.plan", "search", [["event_id", "=", event_id]], limit=1
    )[0]

    configure_id = rpc.exe(
        "event.table.configure.wizard",
        "create",
        [
            {
                "plan_id": plan_id,
                "mode": "replace",
                "table_count": TABLE_COUNT,
                "seats_per_table": SEATS_PER_TABLE,
            }
        ],
    )[0]
    rpc.exe("event.table.configure.wizard", "action_apply", [configure_id])
    rpc.exe(
        "event.table.plan",
        "write",
        [plan_id],
        {"round_count": ROUND_COUNT, "combination_count": 2},
    )
    rpc.exe("event.table.plan", "action_generate_combinations", [plan_id])
    combination_ids = rpc.exe(
        "event.table.combination", "search", [["plan_id", "=", plan_id]]
    )
    rpc.exe("event.table.combination", "action_choose", [combination_ids[0]])

    plan_action = rpc.exe(
        "ir.model.data",
        "search_read",
        [
            ["module", "=", "erplibre_event_table"],
            ["name", "=", "action_event_table_plan"],
        ],
        fields=["res_id"],
    )[0]["res_id"]
    partner_action = rpc.exe(
        "ir.actions.act_window",
        "search",
        [["res_model", "=", "res.partner"]],
        limit=1,
    )[0]
    return {
        "event_id": event_id,
        "plan_id": plan_id,
        "partner_ids": partner_ids,
        "plan_action": plan_action,
        "partner_action": partner_action,
    }


def table_positions(rpc, plan_id):
    """Return {table id: (position_h, position_v)} for the plan."""
    rows = rpc.exe(
        "event.table",
        "search_read",
        [["plan_id", "=", plan_id]],
        fields=["position_h", "position_v"],
    )
    return {r["id"]: (r["position_h"], r["position_v"]) for r in rows}


def seating(rpc, plan_id, round_number):
    """Return {participant id: table id} for one round."""
    rows = rpc.exe(
        "event.table.assignment",
        "search_read",
        [["plan_id", "=", plan_id], ["round_number", "=", round_number]],
        fields=["participant_id", "table_id"],
    )
    return {r["participant_id"][0]: r["table_id"][0] for r in rows}


# --------------------------------------------------------------------------- #
# Selenium harness
# --------------------------------------------------------------------------- #
FLOOR = ".o_event_table_floor_plan"


class FloorPlanUi:
    def __init__(self, driver, url, screenshot_dir):
        self.d = driver
        self.url = url
        self.shot_dir = screenshot_dir
        os.makedirs(screenshot_dir, exist_ok=True)
        self._shot_n = 0

    def shot(self, name):
        self._shot_n += 1
        path = os.path.join(self.shot_dir, f"{self._shot_n:02d}_{name}.png")
        self.d.save_screenshot(path)
        print(f"  screenshot -> {path}")
        return path

    def login(self, user, password):
        self.d.get(f"{self.url}/web/login")
        el = WebDriverWait(self.d, 30).until(
            EC.visibility_of_element_located((By.NAME, "login"))
        )
        time.sleep(1.0)
        el.click()
        el.send_keys(user)
        self.d.find_element(By.NAME, "password").send_keys(password)
        self.d.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        WebDriverWait(self.d, 30).until(
            lambda d: "/odoo" in d.current_url or "/web" in d.current_url
        )

    def open_action(self, action_id, res_id, wait_css):
        for cand in [
            f"{self.url}/odoo/action-{action_id}/{res_id}",
            f"{self.url}/web#action={action_id}&view_type=form&id={res_id}",
        ]:
            self.d.get(cand)
            try:
                WebDriverWait(self.d, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_css))
                )
                return cand
            except TimeoutException:
                continue
        raise RuntimeError(f"could not open action {action_id}/{res_id}")

    def click_button_name(self, name, timeout=20):
        WebDriverWait(self.d, timeout).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, f"button[name='{name}']")
            )
        ).click()

    def toolbar_button(self, label, timeout=20):
        return WebDriverWait(self.d, timeout).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    f"//*[contains(@class,'o_event_table_floor_plan')]"
                    f"//button[normalize-space()='{label}']",
                )
            )
        )

    def select_round(self, round_number):
        self.toolbar_button(str(round_number)).click()
        time.sleep(0.5)

    def blocks(self):
        return self.d.find_elements(
            By.CSS_SELECTOR, f"{FLOOR} .o_event_table_block"
        )

    def badges(self):
        """Name badges, as (participant id, table id, element)."""
        found = []
        for el in self.d.find_elements(
            By.CSS_SELECTOR, f"{FLOOR} [data-participant-id][data-table-id]"
        ):
            found.append(
                (
                    int(el.get_attribute("data-participant-id")),
                    int(el.get_attribute("data-table-id")),
                    el,
                )
            )
        return found

    def drag(self, source, target, dx=0, dy=0):
        chain = ActionChains(self.d)
        chain.move_to_element(source).click_and_hold()
        chain.move_by_offset(15, 0).pause(0.3)
        if target is not None:
            chain.move_to_element(target).pause(0.3)
            chain.move_by_offset(1, 1).pause(0.3)
        else:
            chain.move_by_offset(dx - 15, dy).pause(0.3)
        chain.release().perform()
        time.sleep(1.2)


def make_driver(chromium, chromedriver, headless, window):
    opts = Options()
    if chromium:
        opts.binary_location = chromium
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument(f"--window-size={window}")
    service = Service(chromedriver) if chromedriver else Service()
    driver = webdriver.Chrome(service=service, options=opts)
    w, h = window.split(",")
    driver.set_window_size(int(w), int(h))
    return driver


def resolve_chromedriver(explicit):
    if explicit:
        return explicit
    home = os.path.expanduser("~")
    candidates = []
    for root in (
        os.path.join(home, ".wdm", "drivers", "chromedriver"),
        os.path.join(home, ".cache", "selenium", "chromedriver"),
    ):
        for dirpath, _dirs, files in os.walk(root):
            if "chromedriver" in files:
                candidates.append(os.path.join(dirpath, "chromedriver"))
    # newest path wins (paths carry the version number)
    return sorted(candidates)[-1] if candidates else None


# --------------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------------- #
def run(args):
    rpc = Rpc(args.url, args.db, args.login, args.password)
    ids = setup_data(rpc)
    print(f"Data ready: plan_id={ids['plan_id']} event_id={ids['event_id']}")

    driver = make_driver(
        args.chromium,
        resolve_chromedriver(args.chromedriver),
        args.headless,
        args.window,
    )
    failures = []
    try:
        ui = FloorPlanUi(driver, args.url, args.screenshot_dir)
        ui.login(args.login, args.password)
        print("Logged in.")

        # Scenario 1 - the plan form draws every table of the floor plan.
        ui.open_action(ids["plan_action"], ids["plan_id"], FLOOR)
        WebDriverWait(driver, 20).until(
            lambda d: len(ui.blocks()) == TABLE_COUNT
        )
        ui.shot("plan_form")
        print(f"Scenario 1: {len(ui.blocks())} table blocks drawn")

        # Scenario 2 - every participant of round 1 is seated somewhere.
        seated_1 = ui.badges()
        print(f"Scenario 2: round 1 shows {len(seated_1)} seated people")
        if len(seated_1) != PARTICIPANT_COUNT:
            failures.append(
                f"round 1 shows {len(seated_1)} people "
                f"for {PARTICIPANT_COUNT} participants"
            )
        db_1 = seating(rpc, ids["plan_id"], 1)
        if {p for p, _t, _e in seated_1} != set(db_1):
            failures.append("round 1 badges do not match the assignments")

        # Scenario 3 - switching rounds redraws another seating.
        ui.select_round(2)
        ui.shot("round_2")
        seated_2 = {p: t for p, t, _e in ui.badges()}
        db_2 = seating(rpc, ids["plan_id"], 2)
        print(f"Scenario 3: round 2 shows {len(seated_2)} seated people")
        if seated_2 != db_2:
            failures.append("round 2 badges do not match the assignments")
        if seated_2 == {p: t for p, t, _e in seated_1}:
            failures.append("round 2 seats everyone exactly as round 1")
        ui.select_round(1)

        # Scenario 4 - moving a table stores its new position.
        before = table_positions(rpc, ids["plan_id"])
        ui.toolbar_button("Edit Layout").click()
        time.sleep(0.5)
        ui.drag(ui.blocks()[0], None, dx=120, dy=60)
        ui.shot("table_moved")
        after = table_positions(rpc, ids["plan_id"])
        moved = [k for k in before if before[k] != after[k]]
        print(
            f"Scenario 4: {len(moved)} table(s) moved -> {after.get(moved[0]) if moved else None}"
        )
        if len(moved) != 1:
            failures.append(
                f"{len(moved)} tables changed position, expected exactly 1"
            )
        ui.toolbar_button("Done").click()
        time.sleep(0.5)

        # Scenario 5 - dropping a person onto another swaps their tables.
        badges = ui.badges()
        first = badges[0]
        other = next((b for b in badges if b[1] != first[1]), None)
        if other is None:
            failures.append("every badge of round 1 sits at the same table")
        else:
            ui.drag(first[2], other[2])
            ui.shot("people_swapped")
            db_after = seating(rpc, ids["plan_id"], 1)
            print(
                f"Scenario 5: participant {first[0]} "
                f"{db_1[first[0]]} -> {db_after[first[0]]}, "
                f"participant {other[0]} "
                f"{db_1[other[0]]} -> {db_after[other[0]]}"
            )
            if (db_after[first[0]], db_after[other[0]]) != (
                db_1[other[0]],
                db_1[first[0]],
            ):
                failures.append(
                    "dropping a person onto another did not swap their tables"
                )

        # Scenario 6 - the contact's smart button lists their assignments.
        ui.open_action(
            ids["partner_action"],
            ids["partner_ids"][0],
            "button[name='action_view_table_assignments']",
        )
        ui.click_button_name("action_view_table_assignments")
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".o_list_view, .o_data_row")
            )
        )
        time.sleep(1.0)
        ui.shot("partner_assignments")
        rows = driver.find_elements(By.CSS_SELECTOR, ".o_data_row")
        print(f"Scenario 6: assignment list shows {len(rows)} row(s)")
        if len(rows) != ROUND_COUNT:
            failures.append(
                f"assignment list has {len(rows)} rows "
                f"for {ROUND_COUNT} rounds"
            )

        try:
            for entry in driver.get_log("browser"):
                if entry["level"] == "SEVERE":
                    print("CONSOLE SEVERE:", entry["message"][:300])
        except Exception:
            pass
    finally:
        driver.quit()

    print("\n" + "=" * 60)
    if failures:
        print("RESULT: FAIL")
        for f in failures:
            print("  - " + f)
        return 1
    print("RESULT: PASS - all scenarios succeeded")
    return 0


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default="http://localhost:8069")
    p.add_argument("--db", default="test_erplibre_event_table")
    p.add_argument("--login", default="admin")
    p.add_argument("--password", default="admin")
    p.add_argument(
        "--headless",
        action="store_true",
        help="Run Chromium without a visible window.",
    )
    p.add_argument(
        "--chromium",
        default="/usr/bin/chromium",
        help="Path to the Chromium/Chrome binary.",
    )
    p.add_argument(
        "--chromedriver",
        default=None,
        help="Path to chromedriver (auto-detected if omitted).",
    )
    p.add_argument("--window", default="1400,900")
    p.add_argument(
        "--screenshot-dir",
        default=os.path.join(os.path.dirname(__file__), "screenshots"),
    )
    return p


if __name__ == "__main__":
    sys.exit(run(build_parser().parse_args()))
