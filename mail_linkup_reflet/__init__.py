# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import Command

from . import controllers, models


def uninstall_hook(env):
    """Give the technical features back to every internal user.

    It restores the native implication of ``base.group_no_one`` by
    ``base.group_user`` that ``security/linkup_security.xml`` removes.
    """
    group_no_one = env.ref("base.group_no_one", raise_if_not_found=False)
    group_user = env.ref("base.group_user", raise_if_not_found=False)
    if group_no_one and group_user:
        group_user.write({"implied_ids": [Command.link(group_no_one.id)]})
