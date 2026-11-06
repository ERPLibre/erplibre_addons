#!/usr/bin/env python3
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Measure the response times of LinkUp on the load-test database that
``linkup_bench.py`` creates (LU-NF-028, LU-NF-029).

Each point is measured ``--runs`` times (50 by default, at least 30)
after one warm-up call, as the reference member of the database, the one
with 200 links. The report gives p50, p95 and the maximum, in
milliseconds, with the target of the point when the specification sets
one; the exit status is 1 when a target is missed.

Two modes:

* in-process, the default: the script opens the database and calls the
  methods the web client calls, each time with an empty ORM cache, and
  counts their SQL queries. The sending runs ``action_send`` and the
  commit that writes the bus notifications, in a transaction of its own:
  the notification is then ready for the recipient.
* ``--url http://localhost:18969``: through a running server of the
  database, as the web client does. The sending is measured end to end:
  from the call of ``action_send`` until the websocket of the recipient,
  connected beforehand, receives the card of the reflection.

The points: the Reflet view (``linkup_reflet_view_info``), the graph of
the Network view at each density, the rankings, a link card, "My points"
and the sending of a reflection to the reference member. Each sending is
withdrawn afterwards, so that the database can be measured again.

The HTTP mode logs in as the reference member and as the senders: each
of these accounts receives a new random password, kept in memory and
never shown.

Usage, with the Python of the Odoo environment and ``odoo`` importable:

    python3 linkup_bench_measure.py [-d linkup_bench] [--runs 50]
        [--url http://localhost:18969] [--json <file>]
        -- <options of odoo-bin>
"""

import argparse
import json
import math
import random
import secrets
import sys
import threading
import time

import odoo
from odoo import SUPERUSER_ID, api

REFERENCE_LOGIN = "linkup_bench_0000"
MIN_RUNS = 30
# Targets in milliseconds: LU-NF-028 for the sending, LU-NF-029 for the
# data of the Network view.
SEND_TARGET = 2000
NETWORK_TARGET = 500
MAX_NODES = 50
# Seconds the HTTP mode waits for the card of a sent reflection.
WEBSOCKET_TIMEOUT = 10
DRAFT = {
    "you_said": "Que tu cherches du temps pour ton jardin.",
    "understood": "Que tu as besoin de calme.",
    "real_world_declared": True,
}


def parse_args(argv):
    if "--" in argv:
        index = argv.index("--")
        own, odoo_args = argv[:index], argv[index + 1 :]
    else:
        own, odoo_args = argv, []
    parser = argparse.ArgumentParser(
        description="Measure LinkUp on its load-test database."
    )
    parser.add_argument("-d", "--database", default="linkup_bench")
    parser.add_argument("--runs", type=int, default=50)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--url",
        help="Base URL of a running server of the database: measure"
        " through HTTP and the websocket.",
    )
    parser.add_argument(
        "--json", help="File to write the measures to, as JSON."
    )
    options = parser.parse_args(own)
    if options.runs < MIN_RUNS:
        parser.error(f"--runs must be at least {MIN_RUNS}.")
    return options, odoo_args


def percentile(values, rank):
    """The nearest-rank percentile ``rank`` of ``values``."""
    ordered = sorted(values)
    return ordered[max(math.ceil(rank / 100 * len(ordered)) - 1, 0)]


class Point:
    """The measures of one point, in milliseconds, with the SQL queries
    of each call when the mode counts them."""

    def __init__(self, name, target=None):
        self.name = name
        self.target = target
        self.times = []
        self.queries = []
        self.notes = {}

    def add(self, seconds, queries=None):
        self.times.append(seconds * 1000)
        if queries is not None:
            self.queries.append(queries)

    def summary(self):
        p95 = percentile(self.times, 95)
        return {
            "name": self.name,
            "runs": len(self.times),
            "p50": round(percentile(self.times, 50), 1),
            "p95": round(p95, 1),
            "max": round(max(self.times), 1),
            "queries": max(self.queries) if self.queries else None,
            "target": self.target,
            "met": self.target is None or p95 <= self.target,
            **self.notes,
        }


def reference_data(env):
    """The reference member, and their contacts that hold a direct
    conversation with them, as user ids."""
    reference = env["res.users"].search([("login", "=", REFERENCE_LOGIN)])
    if not reference:
        raise SystemExit(
            f"{REFERENCE_LOGIN} is missing: create the database with"
            " linkup_bench.py."
        )
    links = (
        env["linkup.link"]
        .sudo()
        .search(
            [
                "|",
                ("user_a_id", "=", reference.id),
                ("user_b_id", "=", reference.id),
                ("state", "=", "active"),
                ("channel_id", "!=", False),
            ]
        )
    )
    contacts = sorted(link._linkup_other_user(reference).id for link in links)
    category = env["linkup.category"].search([], limit=1)
    return reference.id, contacts, category.id


def pick_senders(rng, contacts, runs):
    """``runs`` + 1 distinct contacts, one per sending, the first one for
    the warm-up. More runs than contacts ends the script with a message
    instead of an error of ``random.sample``."""
    if runs + 1 > len(contacts):
        raise SystemExit(
            f"--runs {runs} needs {runs + 1} contacts of {REFERENCE_LOGIN}"
            f" with a conversation, the database has {len(contacts)}."
        )
    return rng.sample(contacts, runs + 1)


def screens(rng, contacts):
    """The reading points: name, target, and the call, which takes the
    environment of the reference member."""

    def card(env):
        return env["linkup.link"].get_link_card(rng.choice(contacts))

    return [
        (
            "reflet_view",
            None,
            lambda env: env["linkup.reflet"].linkup_reflet_view_info(),
        ),
        (
            "network_graph_x1",
            NETWORK_TARGET,
            lambda env: env["linkup.link"].get_network_graph(level="x1"),
        ),
        (
            "network_graph_x2",
            NETWORK_TARGET,
            lambda env: env["linkup.link"].get_network_graph(level="x2"),
        ),
        (
            "network_graph_x3",
            NETWORK_TARGET,
            lambda env: env["linkup.link"].get_network_graph(level="x3"),
        ),
        (
            "ranking_partners",
            None,
            lambda env: env["linkup.link"].get_ranking(kind="partners"),
        ),
        (
            "ranking_active_30d",
            None,
            lambda env: env["linkup.link"].get_ranking(
                kind="active", period="30d"
            ),
        ),
        ("link_card", None, card),
        (
            "my_points",
            None,
            lambda env: env["linkup.points.ledger"].linkup_my_points(),
        ),
    ]


def note_graph(point, graph):
    if point.name.startswith("network_graph"):
        point.notes["nodes"] = len(graph["nodes"])
        point.notes["edges"] = len(graph["edges"])


def check_nodes(points):
    """Fail a graph point that draws more than ``MAX_NODES`` nodes."""
    for point in points:
        if point.notes.get("nodes", 0) > MAX_NODES:
            point.target = 0


# ----------------------------------------------------------------------
# In-process
# ----------------------------------------------------------------------


def measure_in_process(registry, options):
    rng = random.Random(options.seed)
    points = []
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        reference_id, contacts, category_id = reference_data(env)
        user_env = api.Environment(cr, reference_id, {})
        for name, target, call in screens(rng, contacts):
            point = Point(name, target)
            call(user_env)
            for _run in range(options.runs):
                user_env.invalidate_all()
                count = cr.sql_log_count
                start = time.perf_counter()
                result = call(user_env)
                point.add(
                    time.perf_counter() - start, cr.sql_log_count - count
                )
            note_graph(point, result)
            points.append(point)
        cr.rollback()
    senders = pick_senders(rng, contacts, options.runs)
    point = Point("send", SEND_TARGET)
    for index, sender_id in enumerate(senders):
        with registry.cursor() as cr:
            env = api.Environment(cr, sender_id, {})
            Reflet = env["linkup.reflet"]
            draft = Reflet.browse(
                Reflet.action_save_draft(dict(DRAFT, category_id=category_id))
            )
            cr.commit()
            env.invalidate_all()
            count = cr.sql_log_count
            start = time.perf_counter()
            draft.action_send(reference_id)
            cr.commit()
            elapsed = time.perf_counter() - start
            if index:
                point.add(elapsed, cr.sql_log_count - count)
            draft.action_withdraw()
            cr.commit()
    points.append(point)
    return points


# ----------------------------------------------------------------------
# HTTP and websocket
# ----------------------------------------------------------------------


class Client:
    """A session of the web client of one account."""

    def __init__(self, url, database, login, password):
        import requests

        self.url = url
        self.session = requests.Session()
        result = self.rpc(
            "/web/session/authenticate",
            {"db": database, "login": login, "password": password},
        )
        if not result.get("uid"):
            raise SystemExit(f"The login of {login} failed.")

    def rpc(self, path, params):
        response = self.session.post(
            self.url + path,
            json={"jsonrpc": "2.0", "method": "call", "params": params},
            timeout=60,
        )
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise RuntimeError(f"{path}: {body['error']['data']['message']}")
        return body["result"]

    def call_kw(self, model, method, args=(), kwargs=None):
        return self.rpc(
            f"/web/dataset/call_kw/{model}/{method}",
            {
                "model": model,
                "method": method,
                "args": list(args),
                "kwargs": kwargs or {},
            },
        )


class Listener:
    """The websocket of a session, read by a thread that stamps the
    arrival of each card of a reflection: ``{reflet id: [(state,
    arrival)]}``."""

    def __init__(self, client):
        import websocket
        from odoo.addons.bus.websocket import WebsocketConnectionHandler

        ws_url = client.url.replace("http", "ws", 1)
        self.socket = websocket.create_connection(
            f"{ws_url}/websocket?version={WebsocketConnectionHandler._VERSION}",
            header=[f"Origin: {client.url}"],
            cookie=f"session_id={client.session.cookies['session_id']}",
        )
        self.socket.send(
            json.dumps(
                {
                    "event_name": "subscribe",
                    "data": {"channels": [], "last": 0},
                }
            )
        )
        self.cards = {}
        self.event = threading.Event()
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        while True:
            try:
                text = self.socket.recv()
            except Exception:
                return
            arrival = time.perf_counter()
            if "linkup.reflet" not in text:
                continue
            for card in find_cards(json.loads(text)):
                self.cards.setdefault(card["id"], []).append(
                    (card.get("state"), arrival)
                )
            self.event.set()

    def wait_card(self, reflet_id, state, timeout):
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            for card_state, arrival in self.cards.get(reflet_id, []):
                if card_state == state:
                    return arrival
            self.event.wait(0.01)
            self.event.clear()
        return None

    def close(self):
        self.socket.close()


def find_cards(value):
    """The cards of reflections anywhere in a bus message: the records of
    ``linkup.reflet`` in the Store data it carries."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "linkup.reflet" and isinstance(item, list):
                yield from (card for card in item if isinstance(card, dict))
            else:
                yield from find_cards(item)
    elif isinstance(value, list):
        for item in value:
            yield from find_cards(item)


def give_passwords(registry, user_ids):
    """New random passwords for ``user_ids``, returned by login."""
    passwords = {}
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        for user in env["res.users"].browse(user_ids):
            passwords[user.login] = secrets.token_urlsafe(9)
            user.password = passwords[user.login]
        cr.commit()
    return passwords


def measure_http(registry, options):
    rng = random.Random(options.seed)
    url = options.url.rstrip("/")
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        reference_id, contacts, category_id = reference_data(env)
    senders = pick_senders(rng, contacts, options.runs)
    passwords = give_passwords(registry, [reference_id] + senders)
    logins = list(passwords)
    reference = Client(url, options.database, logins[0], passwords[logins[0]])
    routes = {
        "reflet_view": lambda: reference.call_kw(
            "linkup.reflet", "linkup_reflet_view_info"
        ),
        "network_graph_x1": lambda: reference.rpc(
            "/linkup/v1/network/graph", {"level": "x1"}
        ),
        "network_graph_x2": lambda: reference.rpc(
            "/linkup/v1/network/graph", {"level": "x2"}
        ),
        "network_graph_x3": lambda: reference.rpc(
            "/linkup/v1/network/graph", {"level": "x3"}
        ),
        "ranking_partners": lambda: reference.rpc(
            "/linkup/v1/network/ranking", {"kind": "partners"}
        ),
        "ranking_active_30d": lambda: reference.rpc(
            "/linkup/v1/network/ranking", {"kind": "active", "period": "30d"}
        ),
        "link_card": lambda: reference.rpc(
            "/linkup/v1/network/link", {"user_id": rng.choice(contacts)}
        ),
        "my_points": lambda: reference.rpc("/linkup/v1/me/points", {}),
    }
    points = []
    for name, target, _call in screens(rng, contacts):
        point = Point(name, target)
        routes[name]()
        for _run in range(options.runs):
            start = time.perf_counter()
            result = routes[name]()
            point.add(time.perf_counter() - start)
        note_graph(point, result)
        points.append(point)
    listener = Listener(reference)
    point = Point("send_to_websocket", SEND_TARGET)
    missed = 0
    try:
        for index, login in enumerate(logins[1:]):
            sender = Client(url, options.database, login, passwords[login])
            draft_id = sender.call_kw(
                "linkup.reflet",
                "action_save_draft",
                [dict(DRAFT, category_id=category_id)],
            )
            start = time.perf_counter()
            sender.call_kw(
                "linkup.reflet", "action_send", [[draft_id], reference_id]
            )
            arrival = listener.wait_card(draft_id, "sent", WEBSOCKET_TIMEOUT)
            if arrival is None:
                missed += 1
            elif index:
                point.add(arrival - start)
            sender.call_kw("linkup.reflet", "action_withdraw", [[draft_id]])
    finally:
        listener.close()
    if missed:
        point.notes["missed"] = missed
        point.target = 0
    points.append(point)
    return points


def main(argv):
    options, odoo_args = parse_args(argv)
    odoo.tools.config.parse_config(odoo_args, setup_logging=True)
    registry = odoo.modules.registry.Registry(options.database)
    if options.url:
        points = measure_http(registry, options)
    else:
        points = measure_in_process(registry, options)
    check_nodes(points)
    rows = [point.summary() for point in points]
    mode = "HTTP" if options.url else "in-process"
    print(f"\nMeasures ({mode}, ms, {options.runs} runs):")
    print(
        f"  {'Point':<20} {'p50':>8} {'p95':>8} {'max':>8} {'queries':>8}"
        f" {'target':>7}  result"
    )
    for row in rows:
        queries = "" if row["queries"] is None else row["queries"]
        target = row["target"] if row["target"] is not None else ""
        extra = ", ".join(
            f"{key} {row[key]}"
            for key in ("nodes", "edges", "missed")
            if key in row
        )
        print(
            f"  {row['name']:<20} {row['p50']:>8} {row['p95']:>8}"
            f" {row['max']:>8} {queries:>8} {target:>7}"
            f"  {'ok' if row['met'] else 'MISSED'} {extra}".rstrip()
        )
    if options.json:
        with open(options.json, "w", encoding="utf-8") as output:
            json.dump({"mode": mode, "points": rows}, output, indent=2)
    if not all(row["met"] for row in rows):
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
