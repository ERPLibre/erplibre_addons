#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsCgModel(models.Model):
    _name = "devops.cg.model"
    _description = "devops_cg_model"
    _order = "sequence, id"

    name = fields.Char(required=True)

    active = fields.Boolean(default=True)

    description = fields.Char()

    devops_workspace_ids = fields.Many2many(
        comodel_name="devops.workspace",
        string="DevOps Workspace",
    )

    has_error = fields.Boolean(
        compute="_compute_has_error",
        store=True,
    )

    has_error_msg = fields.Text(
        compute="_compute_has_error",
        store=True,
    )

    is_to_remove = fields.Boolean(
        help=(
            "Active to tell the code generator to remove by refactoring this"
            " model."
        )
    )

    is_inherit = fields.Boolean(help="If the model inherit another model.")

    is_activity = fields.Boolean(help="Will enable activity and chatter.")

    is_all_tracking = fields.Boolean(
        help="Depend on is_activity, will enable tracking for all fields."
    )

    is_method_compute_company_currency_id = fields.Boolean(
        help="Will write method compute_company_currency_id"
    )

    field_ids = fields.One2many(
        comodel_name="devops.cg.field",
        inverse_name="model_id",
        string="Field",
    )

    module_id = fields.Many2one(
        comodel_name="devops.cg.module",
        string="Module",
        ondelete="cascade",
    )

    sequence = fields.Integer(default=10)

    @api.depends(
        "field_ids.has_error",
    )
    def _compute_has_error(self):
        for rec in self:
            lst_has_error_model = []
            lst_has_error_msg_field = []
            for field_id in rec.field_ids:
                lst_has_error_model.append(field_id.has_error)
                if field_id.has_error:
                    lst_has_error_msg_field.append(
                        f"Field '{field_id.name}' type '{field_id.type}': {field_id.has_error_msg}."
                    )
            rec.has_error = any(lst_has_error_model)
            if rec.has_error:
                rec.has_error_msg = "\n".join(lst_has_error_msg_field)
            else:
                rec.has_error_msg = ""

    def get_field_dct(self):
        self.ensure_one()
        dct_model = {}
        for field_id in self.field_ids:
            dct_model[field_id.name] = field_id.get_dct()
        return dct_model
