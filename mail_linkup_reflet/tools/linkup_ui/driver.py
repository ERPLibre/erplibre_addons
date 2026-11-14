# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Selenium helpers of the LinkUp interface checks.

A ``Run`` holds one browser per persona, the passwords of the acceptance
database (in memory only), and the verdict of every step. A scenario
module exposes ``SECTION``, ``TITLE`` and ``STEPS``, a list of
``(step_id, expected, function)``; each function takes the ``Run``. A
step that raises is ``KO`` with a screenshot of every open browser, and
the steps after it in the same section are ``BLOQUÉ``: they build on it.
A step that raises ``StepDeviation`` is ``KO`` too, but it raises once
the state the next steps build on is reached, so they still play.

Runs with the ERPLibre venv (``selenium`` 4); never imports Odoo.
"""

import json
import os
import re
import subprocess
import time
import traceback

from selenium import webdriver
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

DEFAULT_TIMEOUT = 20

OK = "OK"
KO = "KO"
BLOCKED = "BLOQUÉ"


# Seconds a check of "nothing happened" waits first: a sound, a burst or
# a notification arrives after the answer of the server that causes it.
SETTLE = 3


class StepFailure(AssertionError):
    """A check of a step that does not hold."""


class StepDeviation(StepFailure):
    """A check of a step that does not hold, raised once the step has
    reached the state the next steps of its section build on: the step is
    KO, and the next steps still play."""


def where(error):
    """``[file:line function] `` of the innermost frame of this tool that
    ``error`` went through, or ""."""
    here = os.path.dirname(os.path.abspath(__file__))
    frames = [
        frame
        for frame in traceback.extract_tb(error.__traceback__)
        if os.path.abspath(frame.filename).startswith(here)
    ]
    if not frames:
        return ""
    frame = frames[-1]
    name = os.path.relpath(frame.filename, here)
    return f"[{name}:{frame.lineno} {frame.name}] "


def _slug(text):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[:60]


class Persona:
    """One browser, logged in as one account."""

    def __init__(self, run, login):
        self.run = run
        self.login_name = login
        self.driver = run.new_driver()
        self.driver.set_window_size(1400, 1000)

    # Navigation -----------------------------------------------------

    def goto(self, path):
        self.driver.get(self.run.base_url + path)

    def login(self):
        """Log in through /web/login and wait for the web client."""
        self.goto("/web/login")
        self.type("input[name='login']", self.login_name)
        field = self.find("input[name='password']")
        field.clear()
        field.send_keys(self.run.password(self.login_name))
        self.click("form.oe_login_form button[type='submit']")
        self.wait_webclient()
        return self

    def logout(self):
        self.goto("/web/session/logout")

    def wait_webclient(self, timeout=None):
        """Wait until the web client has mounted and is idle."""
        self.find(".o_web_client", timeout=timeout)
        self.wait_until(
            lambda d: d.execute_script(
                "return document.readyState === 'complete'"
            ),
            "page loaded",
            timeout,
        )
        time.sleep(0.5)

    # Finding --------------------------------------------------------

    def wait_until(self, condition, what, timeout=None):
        try:
            return WebDriverWait(
                self.driver,
                timeout or DEFAULT_TIMEOUT,
                ignored_exceptions=(StaleElementReferenceException,),
            ).until(condition)
        except TimeoutException:
            raise StepFailure(
                f"[{self.login_name}] attendu : {what}"
            ) from None

    def find(self, css, timeout=None, visible=True):
        """The first element matching ``css``, waited for."""

        def found(driver):
            for element in driver.find_elements(By.CSS_SELECTOR, css):
                if not visible or element.is_displayed():
                    return element
            return False

        return self.wait_until(found, f"élément {css}", timeout)

    def finds(self, css, visible=True, attempts=5):
        """Every element matching ``css`` now, without waiting. When the
        page re-renders while the snapshot is read, the whole query runs
        again: a stale element never reads as absent. Raises the stale
        error when the page keeps changing over ``attempts`` snapshots."""
        for attempt in range(attempts):
            try:
                return [
                    element
                    for element in self.driver.find_elements(
                        By.CSS_SELECTOR, css
                    )
                    if not visible or element.is_displayed()
                ]
            except StaleElementReferenceException:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.2)
        return []

    def find_text(self, css, text, timeout=None):
        """The first visible element matching ``css`` whose text contains
        ``text`` (case and spacing as rendered)."""

        def found(driver):
            for element in driver.find_elements(By.CSS_SELECTOR, css):
                try:
                    if element.is_displayed() and text in element.text:
                        return element
                except StaleElementReferenceException:
                    continue
            return False

        return self.wait_until(found, f"{css} contenant « {text} »", timeout)

    def has(self, css, text=None):
        """Whether a visible element matches now, without waiting; a
        re-render while reading runs the query again, as in ``finds``."""
        for attempt in range(5):
            try:
                return any(
                    text is None or text in element.text
                    for element in self.finds(css)
                )
            except StaleElementReferenceException:
                if attempt == 4:
                    raise
                time.sleep(0.2)
        return False

    def wait_gone(self, css, timeout=None):
        self.wait_until(
            lambda d: not any(
                e.is_displayed() for e in d.find_elements(By.CSS_SELECTOR, css)
            ),
            f"disparition de {css}",
            timeout,
        )

    def text(self, css, timeout=None):
        return self.find(css, timeout).text

    # Acting ---------------------------------------------------------

    def _clickable(self, css, text, timeout):
        """The element ``click`` acts on: found, enabled, scrolled to the
        center of the window."""
        element = (
            self.find_text(css, text, timeout)
            if text
            else self.find(css, timeout)
        )
        self.wait_until(
            lambda d: element.is_enabled(), f"{css} actif", timeout
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        return element

    def click(self, css, text=None, timeout=None):
        """Click, with the pointer of the browser, the first visible element
        matching ``css`` (and holding ``text``), once it is enabled. An
        element the page renders again between the lookup and the click is
        looked up once more; any other refusal of the click, such as a
        dialog or an overlay above the element, raises."""
        try:
            element = self._clickable(css, text, timeout)
            element.click()
        except StaleElementReferenceException:
            element = self._clickable(css, text, timeout)
            element.click()
        return element

    def dblclick(self, css, text=None, timeout=None):
        """Double-click, with the pointer of the browser, the first visible
        element matching ``css`` (and holding ``text``), once it is
        enabled, at its center."""
        element = self._clickable(css, text, timeout)
        ActionChains(self.driver).double_click(element).perform()
        return element

    def type(self, css, value, clear=True, timeout=None):
        """Type ``value`` in an input, textarea or contenteditable. A field
        the page renders again before it takes the keys is looked up once
        more: a refused key reaches no field, so nothing is typed twice."""

        def typing():
            element = self.find(css, timeout)
            if clear:
                element.send_keys(Keys.CONTROL, "a")
                element.send_keys(Keys.DELETE)
            element.send_keys(value)
            return element

        try:
            return typing()
        except StaleElementReferenceException:
            return typing()

    def keys(self, *keys, css=None):
        """Send keys to ``css``, looked up once more when the page renders
        it again first, or to the focused element."""
        if not css:
            self.driver.switch_to.active_element.send_keys(*keys)
            return
        try:
            self.find(css).send_keys(*keys)
        except StaleElementReferenceException:
            self.find(css).send_keys(*keys)

    def close_notifications(self, limit=20):
        """Close, each with its close button, the notifications of the web
        client on the screen, as a user does when they cover what comes
        next: they pile up at the top right, over the contacts of the Reflet
        view and the header of a conversation, and stay while the pointer
        rests on them. The pointer first leaves them for the navigation bar
        so that they close by themselves, as for a user who does not hover
        them; those still there after a few seconds are closed by hand.
        Return how many were closed by hand."""
        if not self.finds(".o_notification"):
            return 0
        navbar = self.finds(".o_main_navbar")
        if navbar:
            ActionChains(self.driver).move_to_element(navbar[0]).perform()
        try:
            self.wait_gone(".o_notification", timeout=SETTLE * 3)
            return 0
        except StepFailure:
            pass
        closed = 0
        for _ in range(limit):
            buttons = self.finds(".o_notification .o_notification_close")
            if not buttons:
                break
            try:
                buttons[0].click()
                closed += 1
            except StaleElementReferenceException:
                continue
        return closed

    def pass_tour(self):
        """Skip the LinkUp first-use tour with « Passer la visite » while
        the server holds it pending for this member, then wait until the
        server records it as done. Discuss starts the tour at its first
        opening, and its bubble covers the elements under it. Return
        whether the tour was skipped."""
        login = self.login_name.replace("'", "''")
        rows = self.run.sql(
            "SELECT u.linkup_tour_done, coalesce((SELECT value FROM"
            " ir_config_parameter WHERE key = 'linkup.first_use_tour'), 'True')"
            f" FROM res_users u WHERE u.login = '{login}'"
        )
        if not rows or rows[0][0] == "t" or rows[0][1] == "False":
            return False
        self.click(".o-linkup-Tour-skip", "Passer la visite")
        self.wait_until(
            lambda _d: self.run.sql(
                "SELECT linkup_tour_done FROM res_users"
                f" WHERE login = '{login}'"
            )
            == [["t"]],
            "visite de première utilisation marquée vue",
        )
        self.wait_gone(".o-linkup-Tour-skip")
        return True

    def tab_to(self, css, reverse=False, limit=80):
        """Press Tab (Shift+Tab with ``reverse``) from the focused element
        until the focus is on an element matching ``css``; return the
        number of presses. Raise when ``limit`` presses do not reach it."""
        for count in range(limit + 1):
            if self.js(
                "return Boolean(document.activeElement"
                " && document.activeElement.matches(arguments[0]));",
                css,
            ):
                return count
            chain = ActionChains(self.driver)
            if reverse:
                chain.key_down(Keys.SHIFT).send_keys(Keys.TAB).key_up(
                    Keys.SHIFT
                )
            else:
                chain.send_keys(Keys.TAB)
            chain.perform()
        active = self.js(
            "const e = document.activeElement;"
            " return e ? e.tagName + '.' + e.className : null;"
        )
        raise StepFailure(
            f"[{self.login_name}] {limit} {'Maj+Tab' if reverse else 'Tab'}"
            f" n'atteignent pas {css} (focus sur {active})"
        )

    def js(self, script, *args):
        return self.driver.execute_script(script, *args)

    def rpc(self, model, method, args=None, kwargs=None):
        """Call ``model.method`` as the logged-in user through the web
        client's JSON route, and return its result."""
        return self.driver.execute_async_script(
            """
            const [model, method, args, kwargs, done] = arguments;
            fetch(`/web/dataset/call_kw/${model}/${method}`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({jsonrpc: "2.0", method: "call",
                    params: {model, method, args, kwargs}}),
            }).then(r => r.json()).then(
                r => done(r.error ? {error: r.error.data && r.error.data.message || r.error.message} : {result: r.result}),
                e => done({error: String(e)}));
            """,
            model,
            method,
            args or [],
            kwargs or {},
        )

    def record_sounds(self):
        """Record, from now on, the source of every audio element played
        in the page; ``played_sounds`` reads them back. A page load drops
        the recording. Nothing is heard: the original ``play`` still runs
        and its result is returned unchanged."""
        self.js(
            """
            window.__linkupPlayed = [];
            const proto = HTMLMediaElement.prototype;
            if (!proto.__linkupPlay) {
                proto.__linkupPlay = proto.play;
                proto.play = function () {
                    (window.__linkupPlayed || []).push(this.currentSrc || this.src);
                    return proto.__linkupPlay.apply(this, arguments);
                };
            }
            """
        )

    def _recorded(self, expression, what):
        """The value of a recorder installed in the page; a page loaded
        since then has lost it, which fails rather than reading as
        "nothing happened"."""
        value = self.js(
            f"return {expression} === undefined ? null : {expression};"
        )
        if value is None:
            raise StepFailure(
                f"[{self.login_name}] enregistrement des {what} perdu"
                " (page rechargée depuis son installation)"
            )
        return value

    def played_sounds(self):
        """The sources played since ``record_sounds``, oldest first."""
        return self._recorded("window.__linkupPlayed", "sons")

    def record_notifications(self):
        """Record, from now on, every notification of the web client that
        appears in the page (``.o_notification``), as ``{title, body}``.
        A notification stays on the screen a few seconds only;
        ``recorded_notifications`` reads the record back. A page load
        drops it."""
        self.js(
            """
            if (window.__linkupNotificationsObserver) {
                window.__linkupNotificationsObserver.disconnect();
            }
            const record = [];
            window.__linkupNotifications = record;
            const text = (el, css) => {
                const part = el.querySelector(css);
                return part ? part.textContent.replace(/\\s+/g, " ").trim() : "";
            };
            const take = (el) => record.push({
                title: text(el, ".o_notification_title"),
                body: text(el, ".o_notification_content") || text(el, ".o_notification_body"),
            });
            const observer = new MutationObserver((mutations) => {
                for (const mutation of mutations) {
                    for (const node of mutation.addedNodes) {
                        if (node.nodeType !== Node.ELEMENT_NODE) {
                            continue;
                        }
                        if (node.matches(".o_notification")) {
                            take(node);
                        }
                        node.querySelectorAll(".o_notification").forEach(take);
                    }
                }
            });
            observer.observe(document.body, {childList: true, subtree: true});
            window.__linkupNotificationsObserver = observer;
            """
        )

    def recorded_notifications(self):
        """The ``{title, body}`` seen since ``record_notifications``,
        oldest first."""
        return self._recorded("window.__linkupNotifications", "notifications")

    def drag(self, source_css, target_css, while_over=None):
        """Drag the first visible ``source_css`` onto the first visible
        ``target_css`` with the pointer of the browser: press, a first
        move that starts the drag, a move onto the target's center, then
        release. ``while_over``, when given, is called while the pointer
        rests on the target, the button still pressed; the button is
        released even when it raises. Return what it returns."""
        source = self.find(source_css)
        target = self.find(target_css)
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", source
        )
        ActionChains(self.driver).move_to_element(
            source
        ).click_and_hold().move_by_offset(0, -12).pause(0.2).move_to_element(
            target
        ).pause(
            0.2
        ).perform()
        try:
            return while_over() if while_over else None
        finally:
            ActionChains(self.driver).release().perform()

    def record_points(self):
        """Record, from now on, every points burst that appears in the page
        (a "+N", a "−N", a new rank, a new badge) and every text of the
        points live region. A burst stays on the screen a few seconds
        only; ``recorded_points`` reads the record back. A page load drops
        it."""
        self.js(
            """
            if (window.__linkupPointsObserver) {
                window.__linkupPointsObserver.disconnect();
            }
            const record = {bursts: [], announcements: []};
            window.__linkupPoints = record;
            const take = (el) => record.bursts.push({
                kind: el.dataset.kind || "",
                points: el.dataset.points === undefined ? null : Number(el.dataset.points),
                text: el.textContent.replace(/\\s+/g, " ").trim(),
            });
            const observer = new MutationObserver((mutations) => {
                for (const mutation of mutations) {
                    for (const node of mutation.addedNodes) {
                        if (node.nodeType !== Node.ELEMENT_NODE) {
                            continue;
                        }
                        if (node.matches(".o-linkup-PointsBurst")) {
                            take(node);
                        }
                        node.querySelectorAll(".o-linkup-PointsBurst").forEach(take);
                    }
                }
                const live = document.querySelector(".o-linkup-PointsOverlay-live");
                const text = live ? live.textContent.trim() : "";
                if (text && record.announcements[record.announcements.length - 1] !== text) {
                    record.announcements.push(text);
                }
            });
            observer.observe(document.body, {childList: true, subtree: true, characterData: true});
            window.__linkupPointsObserver = observer;
            """
        )

    def recorded_points(self):
        """``{"bursts": [{kind, points, text}], "announcements": [text]}``
        seen since ``record_points``, oldest first."""
        return self._recorded("window.__linkupPoints", "points")

    def wait_points(self, condition, what, timeout=None):
        """Wait until ``condition(recorded_points())`` holds; return the
        record."""
        return self.wait_until(
            lambda d: condition(self.recorded_points())
            and self.recorded_points(),
            what,
            timeout,
        )

    def screenshot(self, name):
        path = os.path.join(
            self.run.shots_dir, f"{_slug(name)}__{self.login_name}.png"
        )
        try:
            self.driver.save_screenshot(path)
        except WebDriverException:
            return None
        return path

    def quit(self):
        try:
            self.driver.quit()
        except WebDriverException:
            pass


class Run:
    """The browsers, the database and the verdicts of one run."""

    def __init__(self, base_url, database, passwords, out_dir, headless=True):
        self.base_url = base_url.rstrip("/")
        self.database = database
        self._passwords = passwords
        self.out_dir = out_dir
        self.shots_dir = os.path.join(out_dir, "screenshots")
        os.makedirs(self.shots_dir, exist_ok=True)
        self.headless = headless
        self.personas = {}
        self.results = []
        self.memory = {}

    def password(self, login):
        return self._passwords[login]

    def new_driver(self):
        options = webdriver.FirefoxOptions()
        if self.headless:
            options.add_argument("-headless")
        # Calls and video ask for the microphone and the camera: fake
        # devices, granted without a prompt.
        options.set_preference("media.navigator.streams.fake", True)
        options.set_preference("media.navigator.permission.disabled", True)
        options.set_preference("intl.accept_languages", "fr-CA, fr")
        options.set_preference("dom.webnotifications.enabled", False)
        return webdriver.Firefox(options=options)

    def persona(self, login):
        """The browser of ``login``, opened and logged in on first use."""
        if login not in self.personas:
            self.personas[login] = Persona(self, login).login()
        return self.personas[login]

    def close(self, login):
        persona = self.personas.pop(login, None)
        if persona:
            persona.quit()

    def quit(self):
        for login in list(self.personas):
            self.close(login)

    # Database -------------------------------------------------------

    def sql(self, query):
        """Rows of a query on the database, as lists of text. The session
        is read-only: PostgreSQL refuses any write the query attempts."""
        env = dict(os.environ, PGOPTIONS="-c default_transaction_read_only=on")
        out = subprocess.run(
            ["psql", "-d", self.database, "-At", "-F", "\t", "-c", query],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout
        return [line.split("\t") for line in out.splitlines() if line]

    def points(self, login):
        """The karma of ``login``."""
        rows = self.sql(
            "SELECT karma FROM res_users WHERE login = '%s'"
            % login.replace("'", "''")
        )
        return int(rows[0][0]) if rows else None

    # Steps ----------------------------------------------------------

    def check(self, condition, message):
        if not condition:
            raise StepFailure(message)

    def settle(self):
        """Wait ``SETTLE`` seconds before checking that nothing happened."""
        time.sleep(SETTLE)

    def run_section(self, module):
        """Play the steps of a scenario module in order."""
        failed = False
        for step_id, expected, function in module.STEPS:
            entry = {
                "section": module.SECTION,
                "step": step_id,
                "expected": expected,
            }
            if failed:
                entry["verdict"] = BLOCKED
                self.results.append(entry)
                continue
            start = time.monotonic()
            try:
                note = function(self)
                entry["verdict"] = OK
                if note:
                    entry["note"] = str(note)
            except Exception as error:  # noqa: BLE001 - every failure is a KO
                failed = not isinstance(error, StepDeviation)
                entry["verdict"] = KO
                entry["error"] = (
                    str(error)
                    if isinstance(error, StepFailure)
                    else where(error)
                    + "".join(
                        traceback.format_exception_only(type(error), error)
                    ).strip()
                )
                entry["screenshots"] = [
                    p
                    for p in (
                        persona.screenshot(step_id)
                        for persona in self.personas.values()
                    )
                    if p
                ]
            entry["seconds"] = round(time.monotonic() - start, 1)
            self.results.append(entry)
            print(
                f"  {entry['verdict']:<7} {step_id:<8} {expected[:70]}"
                + (
                    f"\n          → {entry['error'][:300]}"
                    if "error" in entry
                    else ""
                ),
                flush=True,
            )

    def write_report(self, title):
        """Write report.json and report.md in the output directory, and
        return the counts by verdict."""
        counts = {}
        for entry in self.results:
            counts[entry["verdict"]] = counts.get(entry["verdict"], 0) + 1
        with open(os.path.join(self.out_dir, "report.json"), "w") as fh:
            json.dump(
                {"title": title, "counts": counts, "steps": self.results},
                fh,
                ensure_ascii=False,
                indent=2,
            )
        lines = [
            f"# {title}",
            "",
            " · ".join(f"{k} {v}" for k, v in sorted(counts.items())),
            "",
            "| Étape | Attendu | Verdict | Détail |",
            "|---|---|---|---|",
        ]
        for entry in self.results:
            detail = entry.get("error") or entry.get("note") or ""
            detail = detail.replace("|", "\\|").replace("\n", " ")[:300]
            lines.append(
                f"| {entry['step']} | {entry['expected']} |"
                f" {entry['verdict']} | {detail} |"
            )
        with open(os.path.join(self.out_dir, "report.md"), "w") as fh:
            fh.write("\n".join(lines) + "\n")
        return counts
