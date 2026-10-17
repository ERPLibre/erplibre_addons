# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.exceptions import UserError


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def button_uninstall(self):
        """Refuse to uninstall erplibre_studio, alone or with a module it
        depends on, while a project has records applied in the database
        and its generated module is not installed: without the studio,
        nothing could revert them, and their external ids would name a
        module that does not exist."""
        res = super().button_uninstall()
        studio = self.search(
            [("name", "=", "erplibre_studio"), ("state", "=", "to remove")]
        )
        if studio:
            projects = self.env["erplibre.studio.project"].sudo()._studio_applied()
            if projects:
                raise UserError(
                    self.env._(
                        "Revert the studio projects %(projects)s first, or "
                        "install their generated modules: what they applied "
                        "would stay in the database with nothing to remove it.",
                        projects=", ".join(projects.mapped("name")),
                    )
                )
        return res
