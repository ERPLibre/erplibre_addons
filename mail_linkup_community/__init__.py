# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from . import controllers, models


def post_init_hook(env):
    """Record the visibility preferences that the accounts already grant,
    when the module that brings them was installed before this one."""
    env["linkup.consent"]._linkup_record_granted_mirrors()
