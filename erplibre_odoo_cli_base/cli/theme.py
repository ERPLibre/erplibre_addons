# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""``theme`` command: apply a website theme from the command line."""

import argparse
import sys
from pathlib import Path

from odoo.cli import Command

from . import _common


def _is_theme(env, module):
    """Tell whether ``module`` matches the website's themes domain.

    False when website is not installed: the domain is website's.
    """
    if "website" not in env:
        return False
    Module = env["ir.module.module"]
    domain = Module.get_themes_domain() + [("id", "=", module.id)]
    return bool(Module.search_count(domain))


class Theme(Command):
    """Install a website theme if needed and apply it to the website"""

    name = "theme"

    def run(self, cmdargs):
        parser = argparse.ArgumentParser(
            prog=f"{Path(sys.argv[0]).name} {self.name}",
            description=self.__doc__.strip(),
        )
        subs = parser.add_subparsers(metavar="ACTION")
        apply = subs.add_parser(
            "apply",
            help="Install THEME if needed, then apply it like the website"
            " 'Choose theme' button.",
            description=(
                "Install THEME (and website) when needed, then do what the"
                " website 'Choose theme' button does on the current"
                " website: remove its theme, set the new one, upgrade the"
                " upstream themes and copy them onto the website."
            ),
        )
        _common.add_global_options(apply)
        apply.add_argument(
            "-d", "--database", required=True, help="database to change"
        )
        apply.add_argument(
            "theme_name", metavar="THEME", help="theme module name"
        )
        apply.set_defaults(handler=self._apply)

        args = parser.parse_args(cmdargs)
        if not hasattr(args, "handler"):
            parser.print_help(sys.stderr)
            sys.exit(1)
        args.handler(args)

    def _apply(self, args):
        """Install the theme when needed, then press 'Choose theme'.

        A theme missing from ir.module.module is looked up again after
        update_list, so a theme added to the addons path after the database
        was created is found. The button runs outside the registry loading,
        so the real website methods apply: _theme_remove of the current
        theme, website.theme_id, upgrade or install of the upstream stream,
        then theme.utils _post_copy. Without a request, the current website
        is the first one.
        """
        _common.parse_odoo_config(args, setup_logging=True)
        name = args.theme_name
        with _common.open_env(args.database) as env:
            Module = env["ir.module.module"]
            theme = Module.search([("name", "=", name)], limit=1)
            if not theme:
                # A module added to the addons path after the database was
                # created has no record yet: refresh the list like the Apps
                # "Update Apps List" button, as -i does before installing.
                Module.update_list()
                theme = Module.search([("name", "=", name)], limit=1)
            if not theme:
                _common.fail(f"No module named {name}.")
            if "website" in env and not _is_theme(env, theme):
                _common.fail(f"{name} is not a website theme.")
            installed_now = False
            if theme.state != "installed":
                theme.button_immediate_install()
                installed_now = True
                theme = env["ir.module.module"].browse(theme.id)
            if not _is_theme(env, theme):
                suffix = " It stays installed." if installed_now else ""
                _common.fail(f"{name} is not a website theme.{suffix}")
            theme.button_choose_theme()
            website = env["website"].get_current_website()
            _common.eprint(f"Theme {name} applied to website {website.id}.")
