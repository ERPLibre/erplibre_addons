# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tools import config


def post_init_hook(env):
    """Refuse the installation on a server started without ``--dev``: the
    module writes the git clones of the checkout. The error rolls the
    installation back."""
    if not config.get("dev_mode"):
        raise UserError(
            env._(
                "erplibre_info_git_fetch is installed only on an Odoo server "
                "started with --dev (for example --dev=all): it writes the "
                "git clones of the checkout."
            )
        )
