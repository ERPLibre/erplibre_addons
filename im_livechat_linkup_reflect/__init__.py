# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from . import controllers, models


def uninstall_hook(env):
    """Delete the reflections that have a visitor as a party, whose
    ``mail.guest`` columns leave with the module: the author of a
    reflection is a member again once the module is gone."""
    env.cr.execute(
        "DELETE FROM linkup_reflet"
        " WHERE author_guest_id IS NOT NULL"
        " OR recipient_guest_id IS NOT NULL"
    )
