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
  connected beforehand, receives the card of the reflection. A server in
  prefork (``--workers`` above 0) serves the websocket on its gevent
  port only: ``--websocket-url ws://localhost:18972`` points the
  websockets there, the origin they announce staying ``--url``.

The points: the Reflet view (``linkup_reflet_view_info``), the graph of
the Network view at each density, the rankings, a link card, "My points"
and the sending of a reflection to the reference member. Each sending is
withdrawn afterwards, so that the database can be measured again.

With ``--concurrency 10 25 50``, the script measures instead, in either
mode, ``N`` members at once at each level ``N``: ``N`` senders, each
with a distinct recipient, drawn from ``--seed`` among the active links
that do not involve the reference member, so that no two senders share
a member. Each round releases ``N`` threads together; each thread sends
one reflection to its recipient and loads one reading screen as the
reference member (the Reflet view or the graph X1, in turn), the even
threads sending first and the odd ones reading first, so that the
readings overlap the sendings. In HTTP, every recipient keeps its
websocket open and the sending is measured until its card arrives
there. A first round, not measured, opens the direct conversation of
each pair, which the websocket of the recipient then subscribes to.
Each point reports, beside its times, the calls that failed and the
cards that did not arrive within ``WEBSOCKET_TIMEOUT``; either one
misses the target. In-process, the threads share the interpreter, as
those of a server with ``--workers 0`` do, and each one holds up to two
connections at once: the PostgreSQL server must accept ``2 N + 4`` of
them beside its other clients.

The HTTP mode logs in as the reference member, the senders and, with
``--concurrency``, the recipients: each of these accounts receives a new
random password, kept in memory and never shown.

Usage, with the Python of the Odoo environment and ``odoo`` importable:

    python3 linkup_bench_measure.py [-d linkup_bench] [--runs 50]
        [--url http://localhost:18969] [--websocket-url <ws url>]
        [--concurrency N [N ...]] [--rounds 4] [--json <file>]
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
from concurrent.futures import ThreadPoolExecutor

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
# The reading screens of a concurrency level, loaded in turn.
CONCURRENT_READS = ("reflet_view", "network_graph_x1")
# In-process, connections a thread holds at most: its transaction, and
# at its commit the cursor on which the bus sends its NOTIFY.
THREAD_CONNECTIONS = 2
# Connections to the database beyond those of the threads, in-process.
SPARE_CONNECTIONS = 4
# Logins at once while the HTTP mode opens its sessions.
LOGIN_THREADS = 8
# Length kept of the message of the first failed call of a point.
ERROR_LENGTH = 200
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
        "--websocket-url",
        help="Base URL of the websockets, such as ws://localhost:18972,"
        " the gevent port of a server in prefork. Defaults to --url.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        nargs="+",
        metavar="N",
        help="Measure N members at once, at each level given, instead of"
        " the points one by one.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=4,
        help="Measured rounds of each concurrency level; more when a"
        f" reading screen would get fewer than {MIN_RUNS} measures.",
    )
    parser.add_argument(
        "--json", help="File to write the measures to, as JSON."
    )
    options = parser.parse_args(own)
    if options.runs < MIN_RUNS:
        parser.error(f"--runs must be at least {MIN_RUNS}.")
    if options.concurrency and min(options.concurrency) < 1:
        parser.error("--concurrency takes levels of 1 or more.")
    if options.rounds < 1:
        parser.error("--rounds must be at least 1.")
    if options.websocket_url and not options.url:
        parser.error("--websocket-url goes with --url.")
    return options, odoo_args


def percentile(values, rank):
    """The nearest-rank percentile ``rank`` of ``values``."""
    ordered = sorted(values)
    return ordered[max(math.ceil(rank / 100 * len(ordered)) - 1, 0)]


class Point:
    """The measures of one point, in milliseconds, with the SQL queries
    of each call when the mode counts them, and the failures: ``errors``
    the calls that raised, ``timeouts`` the cards that did not arrive.
    Threads add to it under its lock."""

    def __init__(self, name, target=None):
        self.name = name
        self.target = target
        self.times = []
        self.queries = []
        self.notes = {}
        self.errors = 0
        self.timeouts = 0
        self.lock = threading.Lock()

    def add(self, seconds, queries=None):
        with self.lock:
            self.times.append(seconds * 1000)
            if queries is not None:
                self.queries.append(queries)

    def fail(self, error=None):
        """Count a call that raised ``error``, or a timeout without it;
        the message of the first error is kept, shortened."""
        with self.lock:
            if error is None:
                self.timeouts += 1
                return
            self.errors += 1
            self.notes.setdefault("first_error", str(error)[:ERROR_LENGTH])

    def summary(self):
        """The row of the point; its times are ``None`` when no call
        succeeded, and the target is missed then too."""
        if self.times:
            p50, p95 = (percentile(self.times, rank) for rank in (50, 95))
            times = [round(value, 1) for value in (p50, p95, max(self.times))]
        else:
            p95 = None
            times = [None] * 3
        return {
            "name": self.name,
            "runs": len(self.times),
            **dict(zip(("p50", "p95", "max"), times)),
            "queries": max(self.queries) if self.queries else None,
            "target": self.target,
            "errors": self.errors,
            "timeouts": self.timeouts,
            "met": p95 is not None
            and not self.errors
            and not self.timeouts
            and (self.target is None or p95 <= self.target),
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


def pick_pairs(env, rng, count, reference_id):
    """``count`` pairs ``(sender, recipient)`` of user ids, from the
    ``active`` links that do not involve the reference member, so that
    the reference member stays the reader of every level. No member
    appears in two pairs; the links are shuffled with ``rng``, and the
    direction of each pair drawn from it."""
    links = (
        env["linkup.link"]
        .sudo()
        .search(
            [
                ("state", "=", "active"),
                ("user_a_id", "!=", reference_id),
                ("user_b_id", "!=", reference_id),
            ],
            order="id",
        )
    )
    rows = [(link.user_a_id.id, link.user_b_id.id) for link in links]
    rng.shuffle(rows)
    pairs, used = [], set()
    for user_a, user_b in rows:
        if user_a in used or user_b in used:
            continue
        used.update((user_a, user_b))
        pairs.append(
            (user_a, user_b) if rng.random() < 0.5 else (user_b, user_a)
        )
        if len(pairs) == count:
            return pairs
    raise SystemExit(
        f"--concurrency {count} needs {count} links without a shared"
        f" member, the database has {len(pairs)}."
    )


def half_life(env):
    """The half-life of the energy in days, 0 without decay, ``None``
    when the network module does not decay the energy."""
    Ledger = env["linkup.points.ledger"]
    if hasattr(Ledger, "_linkup_half_life_days"):
        return Ledger._linkup_half_life_days()
    return None


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
# Concurrency levels
# ----------------------------------------------------------------------


def run_together(count, step):
    """Run ``step(index)`` for each ``index`` of ``range(count)``, each in
    a thread, all released at once by a barrier; return once every thread
    has ended. ``step`` catches its own errors."""
    barrier = threading.Barrier(count)

    def target(index):
        barrier.wait()
        step(index)

    threads = [
        threading.Thread(target=target, args=(index,))
        for index in range(count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


def rounds_for(options, level):
    """The measured rounds of ``level``: ``--rounds``, or more when one
    of the ``CONCURRENT_READS`` would get fewer than ``MIN_RUNS``
    measures, each round reading once per thread."""
    needed = math.ceil(MIN_RUNS * len(CONCURRENT_READS) / level)
    return max(options.rounds, needed)


def warm_up(actors, count):
    """One round of the ``count`` pairs, not measured: it opens the direct
    conversation of each pair, which the websocket of the recipient
    subscribes to only when it connects afterwards."""
    errors = []

    def cycle(index):
        try:
            actors.prepare(index)
            actors.send(index, wait=False)
            actors.withdraw(index)
        except Exception as error:
            errors.append(str(error)[:ERROR_LENGTH])

    run_together(count, cycle)
    if errors:
        raise SystemExit(
            f"The warm-up round failed for {len(errors)} pairs: {errors[0]}"
        )


class Level:
    """The measure of the first ``level`` pairs of ``actors`` at once.

    ``actors`` drives pair ``index``: ``prepare(index)`` saves the draft
    of its sender, ``send(index)`` sends it and returns the seconds until
    the card is delivered, ``None`` when it does not arrive in time,
    ``read(index, name)`` loads a reading screen as the reference member
    and returns ``(seconds, result)``, ``withdraw(index)`` withdraws what
    was sent. Each round saves the drafts, then times the sendings and the
    readings, all in flight together, then withdraws, each phase behind a
    barrier. A failed draft or withdrawal counts as an error of the
    sending.
    """

    def __init__(self, actors, level, send_name):
        self.actors = actors
        self.level = level
        self.sending = Point(send_name, SEND_TARGET)
        self.reading = {
            name: Point(
                name,
                NETWORK_TARGET if name.startswith("network_graph") else None,
            )
            for name in CONCURRENT_READS
        }
        self.ready = set()
        self.round_index = 0

    def measure(self, rounds):
        """Run ``rounds`` rounds; return the points, the sending first."""
        for round_index in range(rounds):
            self.round_index = round_index
            self.ready = set()
            run_together(self.level, self.prepare)
            run_together(self.level, self.step)
            run_together(self.level, self.withdraw)
        return [self.sending, *self.reading.values()]

    def prepare(self, index):
        try:
            self.actors.prepare(index)
            self.ready.add(index)
        except Exception as error:
            self.sending.fail(error)

    def step(self, index):
        """The timed part of a round for pair ``index``: its sending and
        one reading, the even pairs sending first; the reading screen
        changes from one round to the next and between neighbours."""
        name = CONCURRENT_READS[
            (index // 2 + self.round_index) % len(CONCURRENT_READS)
        ]
        if index % 2:
            self.read(index, name)
        if index in self.ready:
            self.send(index)
        if not index % 2:
            self.read(index, name)

    def send(self, index):
        try:
            seconds = self.actors.send(index)
        except Exception as error:
            self.sending.fail(error)
            return
        if seconds is None:
            self.sending.fail()
        else:
            self.sending.add(seconds)

    def read(self, index, name):
        point = self.reading[name]
        try:
            seconds, result = self.actors.read(index, name)
        except Exception as error:
            point.fail(error)
            return
        point.add(seconds)
        note_graph(point, result)

    def withdraw(self, index):
        try:
            self.actors.withdraw(index)
        except Exception as error:
            self.sending.fail(error)


def measure_concurrent(registry, options):
    """Measure each level of ``--concurrency``, in the mode of the
    options; return ``[(level, rounds, points)]``."""
    rng = random.Random(options.seed)
    count = max(options.concurrency)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        reference_id, contacts, category_id = reference_data(env)
        pairs = pick_pairs(env, rng, count, reference_id)
    if options.url:
        actors = HttpActors(
            registry, options, rng, pairs, reference_id, contacts, category_id
        )
        send_name = "send_to_websocket"
    else:
        reads = {name: call for name, _target, call in screens(rng, contacts)}
        actors = InProcessActors(
            registry, pairs, reference_id, category_id, reads
        )
        send_name = "send"
    levels = []
    try:
        warm_up(actors, count)
        actors.listen()
        for level in options.concurrency:
            rounds = rounds_for(options, level)
            points = Level(actors, level, send_name).measure(rounds)
            check_nodes(points)
            levels.append((level, rounds, points))
    finally:
        actors.close()
    return levels


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


class InProcessActors:
    """The pairs of the concurrency levels in the process, for
    ``Level``. Each call opens a cursor of its own, so that the
    threads run in transactions of their own, as the threads of a server
    with ``--workers 0`` do, sharing the interpreter. The sending covers
    ``action_send`` and its commit, as in the sequential mode."""

    def __init__(self, registry, pairs, reference_id, category_id, reads):
        self.registry = registry
        self.pairs = pairs
        self.reference_id = reference_id
        self.category_id = category_id
        self.reads = reads
        self.drafts = {}
        self.sent = set()

    def prepare(self, index):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, self.pairs[index][0], {})
            self.drafts[index] = env["linkup.reflet"].action_save_draft(
                dict(DRAFT, category_id=self.category_id)
            )

    def send(self, index, wait=True):
        sender_id, recipient_id = self.pairs[index]
        with self.registry.cursor() as cr:
            env = api.Environment(cr, sender_id, {})
            draft = env["linkup.reflet"].browse(self.drafts[index])
            start = time.perf_counter()
            draft.action_send(recipient_id)
            cr.commit()
            elapsed = time.perf_counter() - start
        self.sent.add(index)
        return elapsed

    def read(self, index, name):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, self.reference_id, {})
            start = time.perf_counter()
            result = self.reads[name](env)
            elapsed = time.perf_counter() - start
            cr.rollback()
        return elapsed, result

    def withdraw(self, index):
        if index not in self.sent:
            return
        self.sent.discard(index)
        with self.registry.cursor() as cr:
            env = api.Environment(cr, self.pairs[index][0], {})
            env["linkup.reflet"].browse(self.drafts[index]).action_withdraw()

    def listen(self):
        """Nothing to listen to: the in-process sending ends with its
        commit."""

    def close(self):
        """Nothing to close."""


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
    arrival)]}``. It connects to ``ws_url``, by default the server of the
    session, and announces the URL of the session as its origin."""

    def __init__(self, client, ws_url=None):
        import websocket
        from odoo.addons.bus.websocket import WebsocketConnectionHandler

        ws_url = (ws_url or client.url.replace("http", "ws", 1)).rstrip("/")
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


def read_routes(client, rng, contacts):
    """The reading points through the server, as ``client``: ``{name:
    call}``, each call taking no argument and returning the result."""
    return {
        "reflet_view": lambda: client.call_kw(
            "linkup.reflet", "linkup_reflet_view_info"
        ),
        "network_graph_x1": lambda: client.rpc(
            "/linkup/v1/network/graph", {"level": "x1"}
        ),
        "network_graph_x2": lambda: client.rpc(
            "/linkup/v1/network/graph", {"level": "x2"}
        ),
        "network_graph_x3": lambda: client.rpc(
            "/linkup/v1/network/graph", {"level": "x3"}
        ),
        "ranking_partners": lambda: client.rpc(
            "/linkup/v1/network/ranking", {"kind": "partners"}
        ),
        "ranking_active_30d": lambda: client.rpc(
            "/linkup/v1/network/ranking", {"kind": "active", "period": "30d"}
        ),
        "link_card": lambda: client.rpc(
            "/linkup/v1/network/link", {"user_id": rng.choice(contacts)}
        ),
        "my_points": lambda: client.rpc("/linkup/v1/me/points", {}),
    }


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
    routes = read_routes(reference, rng, contacts)
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
    listener = Listener(reference, options.websocket_url)
    point = Point("send_to_websocket", SEND_TARGET)
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
                point.fail()
            elif index:
                point.add(arrival - start)
            sender.call_kw("linkup.reflet", "action_withdraw", [[draft_id]])
    finally:
        listener.close()
    points.append(point)
    return points


class HttpActors:
    """The pairs of the concurrency levels through a running server, for
    ``Level``: a session per sender and per recipient, and a
    session of the reference member per pair for the readings, each used
    by one thread at a time. ``listen`` opens the websocket of each
    recipient; the sending is measured until its card arrives there."""

    def __init__(
        self, registry, options, rng, pairs, reference_id, contacts, category
    ):
        self.pairs = pairs
        self.category_id = category
        self.websocket_url = options.websocket_url
        recipients = [recipient for _sender, recipient in pairs]
        user_ids = [reference_id] + [sender for sender, _r in pairs]
        passwords = give_passwords(registry, user_ids + recipients)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            users = env["res.users"].browse(user_ids + recipients)
            login_of = {user.id: user.login for user in users}
        url = options.url.rstrip("/")
        accounts = (
            [login_of[sender] for sender, _r in pairs]
            + [login_of[recipient] for recipient in recipients]
            + [login_of[reference_id]] * len(pairs)
        )
        with ThreadPoolExecutor(LOGIN_THREADS) as pool:
            clients = list(
                pool.map(
                    lambda login: Client(
                        url, options.database, login, passwords[login]
                    ),
                    accounts,
                )
            )
        count = len(pairs)
        self.senders = clients[:count]
        self.recipients = clients[count : 2 * count]
        self.routes = [
            read_routes(reader, rng, contacts)
            for reader in clients[2 * count :]
        ]
        self.listeners = []
        self.drafts = {}
        self.sent = set()

    def prepare(self, index):
        self.drafts[index] = self.senders[index].call_kw(
            "linkup.reflet",
            "action_save_draft",
            [dict(DRAFT, category_id=self.category_id)],
        )

    def send(self, index, wait=True):
        draft_id = self.drafts[index]
        start = time.perf_counter()
        self.senders[index].call_kw(
            "linkup.reflet", "action_send", [[draft_id], self.pairs[index][1]]
        )
        self.sent.add(index)
        if not wait:
            return None
        arrival = self.listeners[index].wait_card(
            draft_id, "sent", WEBSOCKET_TIMEOUT
        )
        return None if arrival is None else arrival - start

    def read(self, index, name):
        start = time.perf_counter()
        result = self.routes[index][name]()
        return time.perf_counter() - start, result

    def withdraw(self, index):
        if index not in self.sent:
            return
        self.sent.discard(index)
        self.senders[index].call_kw(
            "linkup.reflet", "action_withdraw", [[self.drafts[index]]]
        )

    def listen(self):
        self.listeners = [
            Listener(client, self.websocket_url) for client in self.recipients
        ]

    def close(self):
        for listener in self.listeners:
            listener.close()


def print_rows(title, rows):
    print(f"\n{title}:")
    print(
        f"  {'Point':<20} {'p50':>8} {'p95':>8} {'max':>8} {'queries':>8}"
        f" {'target':>7}  result"
    )
    for row in rows:
        queries = "" if row["queries"] is None else row["queries"]
        target = row["target"] if row["target"] is not None else ""
        extra = ", ".join(
            f"{key} {row[key]}"
            for key in ("nodes", "edges", "errors", "timeouts", "first_error")
            if row.get(key)
        )
        print(
            f"  {row['name']:<20} {row['p50']!s:>8} {row['p95']!s:>8}"
            f" {row['max']!s:>8} {queries:>8} {target:>7}"
            f"  {'ok' if row['met'] else 'MISSED'} {extra}".rstrip()
        )


def main(argv):
    options, odoo_args = parse_args(argv)
    odoo.tools.config.parse_config(odoo_args, setup_logging=True)
    if options.concurrency and not options.url:
        # The pool of Odoo raises rather than waits when it is full: it
        # holds the connections of every thread of the highest level,
        # which the PostgreSQL server must accept too.
        odoo.tools.config["db_maxconn"] = max(
            odoo.tools.config["db_maxconn"],
            max(options.concurrency) * THREAD_CONNECTIONS + SPARE_CONNECTIONS,
        )
    registry = odoo.modules.registry.Registry(options.database)
    with registry.cursor() as cr:
        days = half_life(api.Environment(cr, SUPERUSER_ID, {}))
    mode = "HTTP" if options.url else "in-process"
    report = {"mode": mode, "half_life_days": days}
    if options.concurrency:
        levels = measure_concurrent(registry, options)
        report["levels"] = []
        rows = []
        for level, rounds, points in levels:
            level_rows = [point.summary() for point in points]
            rows += level_rows
            report["levels"].append(
                {"concurrency": level, "rounds": rounds, "points": level_rows}
            )
            print_rows(
                f"Measures ({mode}, ms, {level} members at once,"
                f" {rounds} rounds, half-life {days})",
                level_rows,
            )
    else:
        if options.url:
            points = measure_http(registry, options)
        else:
            points = measure_in_process(registry, options)
        check_nodes(points)
        rows = [point.summary() for point in points]
        report["points"] = rows
        print_rows(
            f"Measures ({mode}, ms, {options.runs} runs, half-life {days})",
            rows,
        )
    if options.json:
        with open(options.json, "w", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
    if not all(row["met"] for row in rows):
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
