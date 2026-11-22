# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.exceptions import UserError

MODULE = "erplibre_studio_generate"


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    def button_uninstall(self):
        """Refuse to uninstall this module, directly or with a module it
        depends on, while custom fields or models without ``x_`` exist
        (``_studio_unprefixed_refusal``). Without this module Odoo no
        longer loads such a field and logs each one as skipped, while their
        rows, their columns and the views of their project that name them
        stay; such a model still loads, but nothing protects it any longer
        from a module of the same name installed later, and the database
        allows names without x_ no more. The uninstall also drops the
        columns that mark them."""
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
        fields and models that carry ``erplibre_studio_unprefixed``, with the
        studio projects that created them; None when there is none. A field
        or a model its generated module defines (state « base ») does not
        count."""
        Fields = self.env["ir.model.fields"].sudo()
        unprefixed = Fields.search(
            [("state", "=", "manual"), ("erplibre_studio_unprefixed", "=", True)],
            order="model, name",
        )
        unprefixed_models = (
            self.env["ir.model"]
            .sudo()
            .search(
                [("state", "=", "manual"), ("erplibre_studio_unprefixed", "=", True)],
                order="model",
            )
        )
        if not (unprefixed or unprefixed_models):
            return None
        reasons = []
        if unprefixed:
            reasons.append(
                self.env._(
                    "the fields %(fields)s have names without x_, which Odoo "
                    "loads only with ERPLibre studio generate",
                    fields=", ".join(f"{f.model}.{f.name}" for f in unprefixed),
                )
            )
        if unprefixed_models:
            reasons.append(
                self.env._(
                    "the models %(models)s have names without x_; ERPLibre "
                    "studio generate protects them from a module of the same "
                    "name installed later",
                    models=", ".join(unprefixed_models.mapped("model")),
                )
            )
        projects = (
            self.env["erplibre.studio.project"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    "|",
                    ("field_ids", "in", unprefixed.ids),
                    ("created_model_ids", "in", unprefixed_models.ids),
                ]
            )
        )
        if not projects:
            return self.env._(
                "Delete them first: %(reasons)s.", reasons="; ".join(reasons)
            )
        return self.env._(
            "Revert the studio projects %(projects)s first, or install their "
            "generated modules: %(reasons)s.",
            projects=", ".join(projects.mapped("name")),
            reasons="; ".join(reasons),
        )
