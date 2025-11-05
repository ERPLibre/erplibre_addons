# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import ast
import logging

from odoo import _, api, exceptions, fields, models, tools

_logger = logging.getLogger(__name__)


class SyncDBResult(models.Model):
    _name = "sync.db.result"
    _description = "Sync db odoo result"
    _order = "sequence, id"

    name = fields.Char(
        compute="_compute_name",
        store=True,
        help="Summary of sync result",
    )

    model_name = fields.Char()

    sequence = fields.Integer(default=5)

    field_name = fields.Char()

    record_id = fields.Integer()

    field_value_local = fields.Char()

    field_value_remote = fields.Char()

    msg = fields.Text()

    data = fields.Text()

    sync_db_id = fields.Many2one(
        comodel_name="sync.db",
        string="Sync DB",
        required=True,
        index=True,
        ondelete="cascade",
    )

    type_result = fields.Selection(
        selection=[
            ("missing_result", "Missing result"),
            ("missing_field", "Missing field"),
            ("missing_model", "Missing model"),
            ("missing_module", "Missing module"),
            ("module_wrong_version", "Module wrong version"),
            ("module_not_installed", "Module not installed"),
            ("diff_value", "Diff value"),
        ],
        help="Type of result detected.",
    )

    colored_line = fields.Selection(
        selection=[
            ("LightYellow", "Warning"),
            ("LightSalmon", "Error"),
            ("Gray", "Sync/not"),
        ],
        compute="_compute_colored_line",
        store=True,
    )

    status = fields.Selection(
        selection=[
            ("not_solve", "Non résolu"),
            ("not_solvable", "Non résoluble"),
            ("solved", "Résolu"),
            ("warning", "Warning"),
            ("error", "Error"),
        ],
        default="not_solve",
    )

    resolution = fields.Selection(
        selection=[
            ("solution_remote", "Solution remote"),
            ("solution_local", "Solution local"),
            ("solution_remote_local", "Solution remote et local"),
        ]
    )

    source = fields.Selection(
        selection=[
            ("local", "Local"),
            ("remote", "Remote"),
        ],
        help="The result affect local instance or remote instance?",
    )

    @api.depends("model_name")
    def _compute_name(self):
        for rec in self:
            rec.name = rec.model_name

    @api.depends("status")
    def _compute_colored_line(self):
        for rec in self:
            if rec.status == "not_solvable":
                rec.colored_line = "Gray"
            elif rec.status == "solved":
                rec.colored_line = "Gray"
            elif rec.status == "warning":
                rec.colored_line = "LightYellow"
            elif rec.status == "error":
                rec.colored_line = "LightSalmon"
            elif rec.status == "not_solve":
                rec.colored_line = False
            else:
                rec.colored_line = False

    def sync_local(self):
        for rec in self:
            if rec.resolution not in [
                "solution_local",
                "solution_remote_local",
            ]:
                continue
            if rec.type_result == "missing_result":
                rec.status = "solved"
                self.env[rec.model_name].create(ast.literal_eval(rec.data))
            elif rec.type_result == "diff_value":
                rec.status = "solved"
                setattr(
                    self.env[rec.model_name].browse(rec.record_id),
                    rec.field_name,
                    rec.field_value_remote,
                )
            else:
                raise exceptions.Warning(
                    _(f"Cannot support type_result '{rec.type_result}'.")
                )

    def sync_remote(self):
        odoo = None
        if self and self[0]:
            odoo = self[0].sync_db_id.get_odoo(self[0].sync_db_id)
        if not odoo:
            raise exceptions.Warning(
                _(f"Cannot support get connexion to remote.")
            )

        for rec in self:
            if rec.resolution not in [
                "solution_remote",
                "solution_remote_local",
            ]:
                continue

            if rec.type_result == "missing_result":
                rec.status = "solved"
                create_id = -1
                while create_id < rec.record_id:
                    data = ast.literal_eval(rec.data)
                    try:
                        create_id = odoo.env[rec.model_name].create(data)
                    except Exception as e:
                        raise e
                    if create_id < rec.record_id:
                        # unlink and create until same id
                        _logger.debug(
                            f"Unlink and recreate {create_id} to"
                            f" {rec.record_id}"
                        )
                        odoo.env[rec.model_name].unlink(create_id)
            elif rec.type_result == "module_not_installed":
                Module = odoo.env["ir.module.module"]
                module_id = Module.search([("name", "=", rec.data)])
                if not module_id:
                    raise exceptions.Warning(
                        _(f"Module '{rec.data}' not existing.")
                    )
                module_check = Module.browse(module_id)
                # Ignore if module already install, maybe installed manually after check sync
                if not module_check.latest_version:
                    status = Module.button_immediate_install(module_id)
                    module_check = Module.browse(module_id)
                    if not module_check.latest_version:
                        raise exceptions.Warning(
                            _(f"Cannot install module '{rec.data}'.")
                        )
                rec.status = "solved"
            elif rec.type_result == "diff_value":
                field_type = (
                    self.env[rec.model_name]._fields.get(rec.field_name).type
                )
                rec.status = "solved"
                v = rec.field_value_local
                if field_type in ("many2many", "one2many"):
                    v = ast.literal_eval(v)
                setattr(
                    odoo.env[rec.model_name].browse(rec.record_id),
                    rec.field_name,
                    v,
                )
            else:
                raise exceptions.Warning(
                    _(f"Cannot support type_result '{rec.type_result}'.")
                )
