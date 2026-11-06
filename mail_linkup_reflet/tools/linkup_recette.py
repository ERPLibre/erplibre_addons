#!/usr/bin/env python3
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Create a local acceptance database of LinkUp, with its demonstration.

The database holds the LinkUp modules and their demonstration data, in
the language given (``fr_CA`` by default). Its accounts are those of the
demonstration, the members of the deck under ``example.com``, plus one
LinkUp administrator (``linkup_admin``) and the system administrator
(``admin``). Each one receives a new random password, printed once on the
standard output and stored nowhere else: Odoo keeps its hash only.

Nothing leaves the machine by email: the email queue cron is archived,
so a queued email, such as a NewLink invitation, stays readable in the
database (``mail.mail``) and is never sent. ``web.base.url`` points to
``http://localhost:<port>``, the address the links of those emails use.

An existing database of that name is kept unless ``--replace`` is given;
``--passwords-only`` gives the accounts of an existing one new
passwords, and changes nothing else.

Usage, with the Python of the Odoo environment and ``odoo`` importable:

    python3 linkup_recette.py [-d linkup_recette] [--replace]
        [--passwords-only] [--lang fr_CA] [--http-port 18969]
        [--modules mail_linkup_gamification] -- <options of odoo-bin>

The options after ``--`` go to the configuration of Odoo, such as
``-c <file>`` or ``--db_host``.
"""

import argparse
import secrets
import sys

import odoo
from odoo import SUPERUSER_ID, Command, api
from odoo.service import db as db_service

# Bytes of randomness of a password; its URL-safe text has 12 characters.
PASSWORD_BYTES = 9
DEMO_MODULE = "mail_linkup_reflet"
ADMIN_GROUP = "mail_linkup_reflet.group_linkup_admin"
LINKUP_ADMIN_LOGIN = "linkup_admin"
TIMEZONE = "America/Toronto"
MAIL_QUEUE_CRON = "mail.ir_cron_mail_scheduler_action"


def parse_args(argv):
    """Split ``argv`` into the options of this script and those of Odoo,
    which follow ``--``."""
    if "--" in argv:
        index = argv.index("--")
        own, odoo_args = argv[:index], argv[index + 1 :]
    else:
        own, odoo_args = argv, []
    parser = argparse.ArgumentParser(
        description="Create a local acceptance database of LinkUp."
    )
    parser.add_argument("-d", "--database", default="linkup_recette")
    parser.add_argument(
        "--modules",
        default="mail_linkup_gamification",
        help="Modules to install, separated by commas; their dependencies"
        " follow.",
    )
    parser.add_argument("--lang", default="fr_CA")
    parser.add_argument(
        "--http-port",
        type=int,
        default=18969,
        help="Port of the links that the emails of the database carry.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Drop the database of that name first, when it exists.",
    )
    parser.add_argument(
        "--passwords-only",
        action="store_true",
        help="Give new passwords to the accounts of an existing database.",
    )
    return parser.parse_args(own), odoo_args


def new_password():
    return secrets.token_urlsafe(PASSWORD_BYTES)


def accounts(env):
    """The accounts of the acceptance: the members of the demonstration
    in id order, the LinkUp administrator and the system administrator."""
    data = env["ir.model.data"].search(
        [
            ("module", "=", DEMO_MODULE),
            ("model", "=", "res.users"),
            ("name", "=like", "demo_user_%"),
        ]
    )
    members = env["res.users"].browse(sorted(data.mapped("res_id")))
    linkup_admin = env["res.users"].search(
        [("login", "=", LINKUP_ADMIN_LOGIN)]
    )
    return members, linkup_admin, env.ref("base.user_admin")


def configure(env, options):
    """Set up the accounts, the email and the base URL of the database,
    and return the passwords given, by login."""
    members, linkup_admin, admin = accounts(env)
    if not members:
        raise SystemExit(
            "The demonstration accounts are missing: the database was"
            " created without demonstration data."
        )
    if not linkup_admin:
        linkup_admin = (
            env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Administration LinkUp",
                    "login": LINKUP_ADMIN_LOGIN,
                    "email": "linkup-admin@example.com",
                    "groups_id": [Command.set([env.ref(ADMIN_GROUP).id])],
                }
            )
        )
    passwords = {}
    for user in members | linkup_admin | admin:
        passwords[user.login] = new_password()
        user.write(
            {
                "password": passwords[user.login],
                "lang": options.lang,
                "tz": TIMEZONE,
            }
        )
    cron = env.ref(MAIL_QUEUE_CRON, raise_if_not_found=False)
    if cron:
        cron.active = False
    parameters = env["ir.config_parameter"]
    parameters.set_param(
        "web.base.url", f"http://localhost:{options.http_port}"
    )
    parameters.set_param("web.base.url.freeze", "True")
    return passwords


def report(env, passwords):
    """Print the accounts with their passwords, and the menus a member
    sees."""
    members, linkup_admin, admin = accounts(env)
    print("\nAccounts of the acceptance database (shown once):")
    print(f"  {'Login':<14} {'Name':<24} {'Role':<22} Password")
    rows = [(user, "member") for user in members]
    rows += [(linkup_admin, "LinkUp administrator")]
    rows += [(admin, "system administrator")]
    for user, role in rows:
        print(
            f"  {user.login:<14} {user.name:<24} {role:<22}"
            f" {passwords[user.login]}"
        )
    member = members[0]
    menus = (
        env["ir.ui.menu"]
        .with_user(member)
        .with_context(lang=member.lang)
        .load_menus(False)
    )
    roots = [menus[menu_id]["name"] for menu_id in menus["root"]["children"]]
    print(f"\nMenus a member sees: {', '.join(roots)}")


def main(argv):
    options, odoo_args = parse_args(argv)
    odoo.tools.config.parse_config(odoo_args, setup_logging=True)
    # The database functions of the service obey this switch of the web
    # manager; this script is a local command and not that manager.
    odoo.tools.config["list_db"] = True
    name = options.database
    exists = name in db_service.list_dbs(True)
    if options.passwords_only:
        if not exists:
            raise SystemExit(f"The database {name} does not exist.")
    elif exists and not options.replace:
        raise SystemExit(
            f"The database {name} exists: --replace drops it first,"
            " --passwords-only gives its accounts new passwords."
        )
    else:
        if exists:
            db_service.exp_drop(name)
        db_service.exp_create_database(
            name, True, options.lang, new_password(), "admin", "CA"
        )
        registry = odoo.modules.registry.Registry(name)
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            if not env["ir.module.module"].search_count(
                [("name", "=", "base"), ("state", "=", "installed")]
            ):
                raise SystemExit(f"The creation of {name} failed.")
            names = set(options.modules.split(","))
            modules = env["ir.module.module"].search(
                [("name", "in", list(names))]
            )
            missing = names - set(modules.mapped("name"))
            if missing:
                raise SystemExit(f"Unknown modules: {', '.join(missing)}")
            modules.button_immediate_install()
    registry = odoo.modules.registry.Registry.new(name)
    with registry.cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        passwords = configure(env, options)
        cr.commit()
        report(env, passwords)


if __name__ == "__main__":
    main(sys.argv[1:])
