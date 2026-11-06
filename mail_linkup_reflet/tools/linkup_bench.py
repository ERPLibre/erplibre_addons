#!/usr/bin/env python3
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Create the load-test database of LinkUp (LU-NF-028, LU-NF-029).

The database holds the six LinkUp modules, without demonstration data,
and a community drawn from a fixed seed, so that two databases created
with the same options hold the same data:

* ``--members`` members (1 000 by default), named after the first names
  of the deck, ``linkup_bench_<n>@example.com``; the reference member,
  ``linkup_bench_0000``, has ``--links`` active links (200 by default);
* the other members have a few links each, mostly ``active``, some
  ``pending`` or ``closed``; about half show their links, about half
  their energy;
* group conversations of a few dozen members, the reference member in
  some of them;
* a direct conversation for each link of the reference member, with the
  carrier messages of its reflections and some free text;
* the reflections of every link, spread over the last year, and the
  points ledger they pay, from which the karma, the ranks and the energy
  of the links follow, as ``_cron_check_karma`` controls them;
* active highlights, some of them to the reference member.

No account receives a password: nobody logs into the database until
``linkup_bench_measure.py`` gives the accounts it uses a random password,
kept in memory and never shown. The administrator gets a random password
at the creation, never shown either. The email queue cron is archived,
so nothing leaves the machine.

Usage, with the Python of the Odoo environment and ``odoo`` importable:

    python3 linkup_bench.py [-d linkup_bench] [--replace] [--seed 1]
        [--members 1000] [--links 200] [--http-port 18969]
        -- <options of odoo-bin>

The options after ``--`` go to the configuration of Odoo, such as
``-c <file>``.
"""

import argparse
import random
import secrets
import sys
import time
from datetime import datetime, timedelta

import odoo
from odoo import SUPERUSER_ID, Command, api
from odoo.service import db as db_service
from psycopg2.extras import execute_values

MODULES = (
    "mail_linkup_reflet",
    "mail_linkup_gamification",
    "mail_linkup_network",
    "mail_linkup_community",
    "mail_linkup_ai",
    "im_livechat_linkup_reflect",
)
MEMBER_GROUP = "mail_linkup_reflet.group_linkup_member"
MAIL_QUEUE_CRON = "mail.ir_cron_mail_scheduler_action"
LOGIN_PREFIX = "linkup_bench_"
REFERENCE_LOGIN = f"{LOGIN_PREFIX}0000"
FIRST_NAMES = (
    "Sam",
    "France",
    "Jacques",
    "Jean",
    "Joanna",
    "Nicolas",
    "Mathieu",
    "Luce",
    "Henri",
    "Jonathan",
    "Thomas",
)
TIMEZONE = "America/Toronto"
# Days the history of the community covers, ending now.
HISTORY_DAYS = 365
# Links of a member other than the reference one: drawn in this range.
OTHER_LINKS = (2, 12)
# Share of the links of other members by state; the rest is ``closed``.
ACTIVE_SHARE = 0.85
PENDING_SHARE = 0.10
# Confirmed reflections of an active link: drawn in this range.
REFLETS_PER_LINK = (1, 6)
# Free text comments of a direct conversation of the reference member.
COMMENTS_PER_CHAT = (2, 8)
# Group conversations: their number, their size, and the number of them
# the reference member belongs to.
GROUP_COUNT = 12
GROUP_SIZE = (20, 60)
REFERENCE_GROUPS = 4
# Shares of the members who show their links, and their energy.
LINKS_VISIBLE_SHARE = 0.5
ENERGY_VISIBLE_SHARE = 0.5
# Highlights: senders to the reference member, and other pairs.
REFERENCE_HIGHLIGHTS = 15
OTHER_HIGHLIGHTS = 100
# Share of the confirmed reflections answered "that's exactly it".
EXACT_SHARE = 0.3
TEXTS = (
    (
        "Que tu cherches du temps pour ton jardin.",
        "Que tu as besoin de calme.",
    ),
    ("Que ton projet avance enfin.", "Que tu te sens fière du chemin fait."),
    ("Que tu veux revoir ta famille.", "Que les tiens te manquent."),
    ("Que le bruit du chantier te pèse.", "Que tu as besoin de repos."),
    ("Que tu aimerais apprendre la guitare.", "Que la musique te nourrit."),
)
BATCH = 500


def parse_args(argv):
    """Split ``argv`` into the options of this script and those of Odoo,
    which follow ``--``."""
    if "--" in argv:
        index = argv.index("--")
        own, odoo_args = argv[:index], argv[index + 1 :]
    else:
        own, odoo_args = argv, []
    parser = argparse.ArgumentParser(
        description="Create the load-test database of LinkUp."
    )
    parser.add_argument("-d", "--database", default="linkup_bench")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--members", type=int, default=1000)
    parser.add_argument(
        "--links",
        type=int,
        default=200,
        help="Active links of the reference member.",
    )
    parser.add_argument("--lang", default="fr_CA")
    parser.add_argument(
        "--http-port",
        type=int,
        default=18969,
        help="Port of web.base.url, which the websocket of the measure"
        " checks its origin against.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Drop the database of that name first, when it exists.",
    )
    options = parser.parse_args(own)
    if options.links >= options.members:
        parser.error("--links must be lower than --members.")
    return options, odoo_args


def new_password():
    return secrets.token_urlsafe(9)


def step(message, start):
    print(f"  {message} ({time.monotonic() - start:.1f} s)", flush=True)


class Generator:
    """Draw the community of the database from ``options.seed``.

    Each step writes through the ORM where LinkUp has a behaviour to
    keep, and in SQL where the volume makes the ORM slow and no override
    applies: the links, the reflections of the pairs without a direct
    conversation and the ledger lines.
    """

    def __init__(self, env, options):
        self.env = env
        self.cr = env.cr
        self.options = options
        self.rng = random.Random(options.seed)
        self.now = datetime.now().replace(microsecond=0)
        self.start = time.monotonic()

    def past(self, low=0, high=HISTORY_DAYS):
        """A random moment between ``high`` and ``low`` days ago."""
        seconds = self.rng.randint(low * 86400, high * 86400)
        return self.now - timedelta(seconds=seconds)

    def run(self):
        self.configure()
        self.create_members()
        self.create_links()
        self.create_groups()
        self.create_chats()
        self.create_reflets()
        self.create_ledger()
        self.create_highlights()
        self.env.flush_all()
        self.cr.execute("ANALYZE")
        step("statistics", self.start)

    def configure(self):
        cron = self.env.ref(MAIL_QUEUE_CRON, raise_if_not_found=False)
        if cron:
            cron.active = False
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param(
            "web.base.url", f"http://localhost:{self.options.http_port}"
        )
        parameters.set_param("web.base.url.freeze", "True")

    def create_members(self):
        """The members, by batches, their accounts dated back before the
        history so that each one earns points; then their network
        preferences, through the ORM, which records the consents that
        mirror them."""
        Users = (
            self.env["res.users"]
            .sudo()
            .with_context(
                no_reset_password=True,
                mail_create_nolog=True,
                mail_create_nosubscribe=True,
                tracking_disable=True,
            )
        )
        group = self.env.ref(MEMBER_GROUP)
        vals_list = []
        for index in range(self.options.members):
            login = f"{LOGIN_PREFIX}{index:04d}"
            vals_list.append(
                {
                    "name": f"{FIRST_NAMES[index % len(FIRST_NAMES)]}"
                    f" {index:04d}",
                    "login": login,
                    "email": f"{login}@example.com",
                    "groups_id": [Command.set(group.ids)],
                    "lang": self.options.lang,
                    "tz": TIMEZONE,
                }
            )
        users = Users.browse()
        for offset in range(0, len(vals_list), 100):
            users |= Users.create(vals_list[offset : offset + 100])
        self.users = users
        self.reference = users[0]
        self.env.flush_all()
        self.cr.execute(
            "UPDATE res_users SET create_date = %s WHERE id IN %s",
            [
                self.now - timedelta(days=HISTORY_DAYS + 30),
                tuple(users.ids),
            ],
        )
        users.invalidate_recordset(["create_date"])
        links_visible = users.filtered(
            lambda _user: self.rng.random() < LINKS_VISIBLE_SHARE
        )
        energy_visible = users.filtered(
            lambda _user: self.rng.random() < ENERGY_VISIBLE_SHARE
        )
        links_visible.write({"linkup_links_visible": True})
        energy_visible.write({"linkup_energy_visible": True})
        step(f"{len(users)} members", self.start)

    def create_links(self):
        """The links: the reference member with the next ``--links``
        members, every other member with a few drawn ones. Stored in SQL,
        each pair ordered as ``linkup.link.create`` stores it."""
        ids = self.users.ids
        reference = ids[0]
        pairs = {}
        for other in ids[1 : self.options.links + 1]:
            pairs[(reference, other)] = "active"
        others = ids[1:]
        for user_id in others:
            for _index in range(self.rng.randint(*OTHER_LINKS)):
                other = self.rng.choice(others)
                if other == user_id:
                    continue
                pair = tuple(sorted((user_id, other)))
                if pair in pairs:
                    continue
                draw = self.rng.random()
                if draw < ACTIVE_SHARE:
                    state = "active"
                elif draw < ACTIVE_SHARE + PENDING_SHARE:
                    state = "pending"
                else:
                    state = "closed"
                pairs[pair] = state
        rows = []
        for (user_a, user_b), state in sorted(pairs.items()):
            first = self.past(30) if state == "active" else None
            last = self.past(0, 30) if state == "active" else self.past(0, 60)
            rows.append(
                (
                    user_a,
                    user_b,
                    state,
                    first,
                    last,
                    0,
                    0,
                    SUPERUSER_ID,
                    self.now,
                    SUPERUSER_ID,
                    self.now,
                )
            )
        returned = execute_values(
            self.cr._obj,
            """
            INSERT INTO linkup_link
                (user_a_id, user_b_id, state, first_link_date,
                 last_interaction_date, energy_a, energy_b,
                 create_uid, create_date, write_uid, write_date)
            VALUES %s RETURNING id
            """,
            rows,
            page_size=BATCH,
            fetch=True,
        )
        self.env["linkup.link"].invalidate_model()
        self.links = (
            self.env["linkup.link"].sudo().browse([row[0] for row in returned])
        )
        step(f"{len(self.links)} links", self.start)

    def create_groups(self):
        """The group conversations, the reference member in the first
        ``REFERENCE_GROUPS`` of them. ``install_mode`` keeps the creation
        from adding the superuser to them."""
        Channel = (
            self.env["discuss.channel"].sudo().with_context(install_mode=True)
        )
        others = self.users[1:]
        for index in range(GROUP_COUNT):
            size = self.rng.randint(*GROUP_SIZE)
            members = others.browse(
                self.rng.sample(others.ids, min(size, len(others)))
            )
            if index < REFERENCE_GROUPS:
                members |= self.reference
            Channel.create(
                {
                    "name": f"Groupe {index + 1:02d}",
                    "channel_type": "group",
                    "channel_member_ids": [
                        Command.create({"partner_id": partner.id})
                        for partner in members.partner_id
                    ],
                }
            )
        step(f"{GROUP_COUNT} group conversations", self.start)

    def create_chats(self):
        """A direct conversation for each link of the reference member,
        kept on the link, as ``linkup.reflet._linkup_direct_channel``
        keeps it. ``install_mode`` keeps the creation from adding the
        superuser to the chat, which holds its two parties only."""
        Channel = (
            self.env["discuss.channel"].sudo().with_context(install_mode=True)
        )
        reference = self.reference
        self.reference_links = self.links.filtered(
            lambda link: reference in (link.user_a_id | link.user_b_id)
        )
        for link in self.reference_links:
            other = link._linkup_other_user(reference)
            channel = Channel.create(
                {
                    "name": f"{reference.name}, {other.name}",
                    "channel_type": "chat",
                    "channel_member_ids": [
                        Command.create({"partner_id": partner.id})
                        for partner in (reference | other).partner_id
                    ],
                }
            )
            link.channel_id = channel
        step(f"{len(self.reference_links)} direct conversations", self.start)

    def create_reflets(self):
        """The reflections of every link, oldest first in each pair.

        An ``active`` link holds confirmed ones, a ``pending`` link one
        sent and waiting, a ``closed`` link one rejected. The carrier
        message of a reflection of the reference member is a ``comment``
        of the direct conversation of the pair, authored by its author,
        with the neutral sentence of ``_linkup_carrier_text``; free text
        follows in the conversation.
        """
        categories = self.env["linkup.category"].sudo().search([])
        rows = []
        for link in self.links:
            pair = (link.user_a_id.id, link.user_b_id.id)
            if link.state == "active":
                count = self.rng.randint(*REFLETS_PER_LINK)
                states = ["confirmed"] * count
            elif link.state == "pending":
                states = ["sent"]
            else:
                states = ["rejected"]
            start = link.first_link_date or self.past(30)
            for state in states:
                author, recipient = pair
                if self.rng.random() < 0.5:
                    author, recipient = recipient, author
                you_said, understood = self.rng.choice(TEXTS)
                sent = start + timedelta(
                    seconds=self.rng.randint(0, 20 * 86400)
                )
                sent = min(sent, self.now - timedelta(hours=1))
                answered = (
                    sent + timedelta(hours=self.rng.randint(1, 48))
                    if state != "sent"
                    else None
                )
                if answered:
                    answered = min(answered, self.now)
                rows.append(
                    (
                        author,
                        recipient,
                        link.id,
                        link.channel_id.id or None,
                        "initial",
                        self.rng.choice(categories.ids),
                        you_said,
                        understood,
                        True,
                        sent.date(),
                        state,
                        "none",
                        "none",
                        sent,
                        answered,
                        answered,
                        0,
                        author,
                        sent,
                        author,
                        answered or sent,
                    )
                )
        returned = execute_values(
            self.cr._obj,
            """
            INSERT INTO linkup_reflet
                (author_id, recipient_id, link_id, channel_id, kind,
                 category_id, you_said, understood, real_world_declared,
                 real_world_date, state, response_state, guess_state,
                 sent_date, read_date, answered_date, round_index,
                 create_uid, create_date, write_uid, write_date)
            VALUES %s RETURNING id
            """,
            rows,
            page_size=BATCH,
            fetch=True,
        )
        Reflet = self.env["linkup.reflet"]
        Reflet.invalidate_model()
        self.reflets = Reflet.sudo().browse([row[0] for row in returned])
        step(f"{len(self.reflets)} reflections", self.start)
        self.create_messages()

    def create_messages(self):
        """The carrier messages and the free text of the direct
        conversations of the reference member."""
        Message = self.env["mail.message"].sudo()
        comment = self.env.ref("mail.mt_comment")
        carriers = self.reflets.filtered("channel_id")
        vals_list = []
        for reflet in carriers:
            vals_list.append(
                {
                    "model": "discuss.channel",
                    "res_id": reflet.channel_id.id,
                    "message_type": "comment",
                    "subtype_id": comment.id,
                    "author_id": reflet.author_id.partner_id.id,
                    "body": f"<p>{reflet._linkup_carrier_text()}</p>",
                    "date": reflet.sent_date,
                }
            )
        messages = Message.browse()
        for offset in range(0, len(vals_list), BATCH):
            messages |= Message.create(vals_list[offset : offset + BATCH])
        self.env.flush_all()
        execute_values(
            self.cr._obj,
            "UPDATE linkup_reflet SET message_id = data.message_id"
            " FROM (VALUES %s) AS data (id, message_id)"
            " WHERE linkup_reflet.id = data.id",
            list(zip(carriers.ids, messages.ids)),
            page_size=BATCH,
        )
        self.env["linkup.reflet"].invalidate_model(["message_id"])
        vals_list = []
        for link in self.reference_links:
            partners = (link.user_a_id | link.user_b_id).partner_id
            for _index in range(self.rng.randint(*COMMENTS_PER_CHAT)):
                vals_list.append(
                    {
                        "model": "discuss.channel",
                        "res_id": link.channel_id.id,
                        "message_type": "comment",
                        "subtype_id": comment.id,
                        "author_id": self.rng.choice(partners.ids),
                        "body": "<p>Merci pour ce moment, à bientôt !</p>",
                        "date": self.past(0, 30),
                    }
                )
        for offset in range(0, len(vals_list), BATCH):
            Message.create(vals_list[offset : offset + BATCH])
        step(
            f"{len(messages)} carrier messages, {len(vals_list)} comments",
            self.start,
        )

    def create_ledger(self):
        """The ledger lines the reflections pay, in SQL, as
        ``linkup.points.ledger._linkup_insert`` writes them; then the
        energy of each link and the karma of each member, a single karma
        change per member, so that the karma equals the sum of the
        lines."""
        Rule = self.env["linkup.points.rule"].sudo()
        rules = {rule.code: rule for rule in Rule.search([])}
        rows = []

        def line(rule, user, other, reflet, date):
            rows.append(
                (
                    user,
                    other,
                    rule.id,
                    rule.points,
                    False,
                    None,
                    date,
                    reflet.channel_id.id or None,
                    reflet.message_id.id or None,
                    reflet.id,
                    reflet.link_id.id,
                    f"bench:{reflet.id}",
                    False,
                    None,
                    SUPERUSER_ID,
                    date,
                    SUPERUSER_ID,
                    date,
                )
            )

        for reflet in self.reflets:
            author = reflet.author_id.id
            recipient = reflet.recipient_id.id
            date = reflet.answered_date or reflet.sent_date
            if reflet.state == "confirmed":
                line(rules["reflect_sent"], author, recipient, reflet, date)
                for user, other in ((author, recipient), (recipient, author)):
                    line(rules["reflect_confirmed"], user, other, reflet, date)
                if self.rng.random() < EXACT_SHARE:
                    for user, other in (
                        (author, recipient),
                        (recipient, author),
                    ):
                        line(rules["answer_exact"], user, other, reflet, date)
            elif reflet.state == "rejected":
                line(
                    rules["reflect_rejected"], author, recipient, reflet, date
                )
        execute_values(
            self.cr._obj,
            """
            INSERT INTO linkup_points_ledger
                (user_id, partner_user_id, rule_id, points, capped,
                 cap_reason, date, channel_id, message_id, reflet_id,
                 link_id, event_key, resets_decay, decay_day,
                 create_uid, create_date, write_uid, write_date)
            VALUES %s
            """,
            rows,
            page_size=BATCH,
        )
        self.cr.execute(
            """
            UPDATE linkup_link SET
                energy_a = COALESCE(sums.energy_a, 0),
                energy_b = COALESCE(sums.energy_b, 0)
            FROM (
                SELECT line.link_id,
                    SUM(line.points) FILTER (
                        WHERE line.user_id = link.user_a_id) AS energy_a,
                    SUM(line.points) FILTER (
                        WHERE line.user_id = link.user_b_id) AS energy_b
                FROM linkup_points_ledger line
                JOIN linkup_link link ON link.id = line.link_id
                GROUP BY line.link_id
            ) AS sums
            WHERE linkup_link.id = sums.link_id
            """
        )
        self.env["linkup.link"].invalidate_model()
        self.cr.execute(
            "SELECT user_id, SUM(points) FROM linkup_points_ledger"
            " GROUP BY user_id"
        )
        karma = dict(self.cr.fetchall())
        self.env["gamification.karma.tracking"].sudo().create(
            [
                {
                    "user_id": user_id,
                    "old_value": 0,
                    "new_value": points,
                    "reason": "LinkUp",
                }
                for user_id, points in sorted(karma.items())
                if points
            ]
        )
        step(f"{len(rows)} ledger lines", self.start)

    def create_highlights(self):
        """Active highlights: some contacts of the reference member to
        them, and pairs drawn among the active links of the others."""
        Highlight = self.env["linkup.highlight"].sudo()
        reference = self.reference
        senders = self.rng.sample(
            [
                link._linkup_other_user(reference).id
                for link in self.reference_links
            ],
            min(REFERENCE_HIGHLIGHTS, len(self.reference_links)),
        )
        vals_list = [
            {"sender_id": sender, "recipient_id": reference.id}
            for sender in senders
        ]
        actives = (self.links - self.reference_links).filtered(
            lambda link: link.state == "active"
        )
        for link in self.rng.sample(
            list(actives), min(OTHER_HIGHLIGHTS, len(actives))
        ):
            sender, recipient = link.user_a_id.id, link.user_b_id.id
            if self.rng.random() < 0.5:
                sender, recipient = recipient, sender
            vals_list.append({"sender_id": sender, "recipient_id": recipient})
        Highlight.create(vals_list)
        step(f"{len(vals_list)} highlights", self.start)


def report(env):
    """Print what the database holds, and its reference member."""
    reference = env["res.users"].search([("login", "=", REFERENCE_LOGIN)])
    Link = env["linkup.link"].sudo()
    counts = {
        "members": env["res.users"].search_count(
            [("login", "=like", f"{LOGIN_PREFIX}%")]
        ),
        "links": Link.search_count([]),
        "links of the reference member": Link.search_count(
            [
                "|",
                ("user_a_id", "=", reference.id),
                ("user_b_id", "=", reference.id),
                ("state", "=", "active"),
            ]
        ),
        "reflections": env["linkup.reflet"].sudo().search_count([]),
        "ledger lines": env["linkup.points.ledger"].sudo().search_count([]),
        "conversations": env["discuss.channel"].sudo().search_count([]),
    }
    print("\nLoad-test database:")
    for label, count in counts.items():
        print(f"  {label:<32} {count}")
    print(f"  {'reference member':<32} {reference.login} ({reference.name})")


def main(argv):
    options, odoo_args = parse_args(argv)
    odoo.tools.config.parse_config(odoo_args, setup_logging=True)
    # The database functions of the service obey this switch of the web
    # manager; this script is a local command and not that manager.
    odoo.tools.config["list_db"] = True
    name = options.database
    if name in db_service.list_dbs(True):
        if not options.replace:
            raise SystemExit(
                f"The database {name} exists: --replace drops it first."
            )
        db_service.exp_drop(name)
    db_service.exp_create_database(
        name, False, options.lang, new_password(), "admin", "CA"
    )
    registry = odoo.modules.registry.Registry(name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        modules = env["ir.module.module"].search([("name", "in", MODULES)])
        missing = set(MODULES) - set(modules.mapped("name"))
        if missing:
            raise SystemExit(f"Unknown modules: {', '.join(sorted(missing))}")
        modules.button_immediate_install()
    registry = odoo.modules.registry.Registry.new(name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        Generator(env, options).run()
        cr.commit()
        report(env)


if __name__ == "__main__":
    main(sys.argv[1:])
