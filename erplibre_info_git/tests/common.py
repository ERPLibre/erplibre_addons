# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.addons.erplibre_info.tests.common import ErplibreInfoCase


class ErplibreInfoGitCase(ErplibreInfoCase):
    """The fake checkout of erplibre_info, and the snapshot model."""

    def setUp(self):
        super().setUp()
        self.Snapshot = self.env["erplibre.code.snapshot"]
