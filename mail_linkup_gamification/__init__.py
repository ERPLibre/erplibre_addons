# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from . import controllers, models


def uninstall_hook(env):
    """Take the points of the ledger out of the karma before the ledger
    leaves with the module."""
    env["linkup.points.ledger"]._linkup_remove_karma()
