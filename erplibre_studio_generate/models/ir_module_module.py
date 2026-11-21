# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.exceptions import UserError

MODULE = "erplibre_studio_generate"


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def button_uninstall(self):
        """Refuse to uninstall this module, directly or with a module it
        depends on, while custom fields without ``x_`` exist
        (``_studio_unprefixed_refusal``). Without this module Odoo no
        longer loads them and logs each one as skipped, while their rows,
        their columns and the views of their project that name them stay;
        the uninstall also drops the column that marks them."""
        result = super().button_uninstall()
        removed = self.sudo().search(
            [("name", "=", MODULE), ("state", "=", "to remove")]
        )
        if removed:
            refusal = self._studio_unprefixed_refusal()
            if refusal:
                raise UserError(refusal)
        return result

    def _studio_unprefixed_refusal(self):
        """Why ERPLibre studio generate cannot be uninstalled: the custom
        fields that carry ``erplibre_studio_unprefixed``, with the studio
        projects that created them; None when there is none. A field its
        generated module defines (state « base ») does not count."""
        Fields = self.env["ir.model.fields"].sudo()
        unprefixed = Fields.search(
            [("state", "=", "manual"), ("erplibre_studio_unprefixed", "=", True)],
            order="model, name",
        )
        if not unprefixed:
            return None
        names = ", ".join(f"{f.model}.{f.name}" for f in unprefixed)
        projects = (
            self.env["erplibre.studio.project"]
            .sudo()
            .with_context(active_test=False)
            .search([("field_ids", "in", unprefixed.ids)])
        )
        if not projects:
            return self.env._(
                "Delete the fields %(fields)s first: their names have no x_, "
                "which Odoo loads only with ERPLibre studio generate.",
                fields=names,
            )
        return self.env._(
            "Revert the studio projects %(projects)s first, or install their "
            "generated modules: the fields %(fields)s have names without x_, "
            "which Odoo loads only with ERPLibre studio generate.",
            projects=", ".join(projects.mapped("name")),
            fields=names,
        )
