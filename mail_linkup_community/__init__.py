# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo.tools import SQL

from . import controllers, models
from .models.linkup_rate_event import LOCK_TABLE


def post_init_hook(env):
    """Record the visibility preferences that the accounts already grant,
    when the module that brings them was installed before this one."""
    env["linkup.consent"]._linkup_record_granted_mirrors()


def uninstall_hook(env):
    """Drop the table of the locks of the limits, which the ORM does not
    know and so leaves behind (``linkup.rate.event._linkup_lock``)."""
    env.cr.execute(SQL("DROP TABLE IF EXISTS %s", SQL.identifier(LOCK_TABLE)))
