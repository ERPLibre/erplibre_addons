# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, models


class CodeGeneratorModule(models.Model):
    _inherit = "code.generator.module"

    @api.depends_context("erplibre_studio_version")
    def _get_latest_version(self):
        """The manifest version comes from ``installed_version``, which Odoo
        reads from the module on the addons path. A studio generation
        gives it in the context instead."""
        super()._get_latest_version()
        version = self.env.context.get("erplibre_studio_version")
        if version:
            for module in self:
                module.installed_version = version
