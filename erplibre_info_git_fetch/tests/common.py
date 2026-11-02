# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.erplibre_info_git.tests.common import ErplibreInfoGitCase


class ErplibreInfoGitFetchCase(ErplibreInfoGitCase):
    """The fake checkout and the snapshot model, for the server actions;
    ``server_actions_allowed(dev=False)`` stands for a server started
    without ``--dev``."""
