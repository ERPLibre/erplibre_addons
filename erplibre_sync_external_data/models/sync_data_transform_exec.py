import json
import logging
import os

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SyncDataTransformExec(models.Model):
    _name = "sync.data.transform.exec"
    _description = "sync_data_transform_exec"
    _order = "id"

    name = fields.Char(compute="_compute_name", store=True)

    to_model_name = fields.Char(
        string="To model",
        help="To model name reference",
        required=True,
        index=True,
    )

    to_id_ref = fields.Many2oneReference(
        string="To ID reference",
        index=True,
        help="Id of the followed resource",
        model_field="to_model_name",
    )

    sync_data_transform_id = fields.Many2one(
        comodel_name="sync.data.transform", string="Sync Data Transform"
    )

    from_id_ref = fields.Many2oneReference(
        string="From ID",
        index=True,
        help="From ID reference",
        model_field="from_model_name",
    )

    from_model_name = fields.Char(
        string="From Model", help="From model name reference"
    )

    note = fields.Html()

    modification = fields.Text()

    modification_done = fields.Boolean(readonly=True)

    has_no_match = fields.Boolean(readonly=True)

    need_review = fields.Boolean()

    msg_review = fields.Html()

    msg_review_reason = fields.Char()

    method = fields.Selection(
        selection=[("create", "Create"), ("write", "Update")]
    )

    depend_ids = fields.Many2many(
        comodel_name="sync.data.transform.exec",
        relation="sync_data_transform_exec_depend_rel",
        column1="parent_id",
        column2="child_id",
    )

    id_depend_name = fields.Char(
        help="To fill parent depend_ids",
        default=lambda self: f"#REPLACE.{os.urandom(8).hex()}",
    )

    hash_generic_value = fields.Char(
        help="This hash can help to remove duplication, hash generic value before adding depend hash."
    )

    associate_key = fields.Char(
        help="Help child dependency to find his parent."
    )

    @api.depends(
        "method",
        "to_model_name",
        "to_id_ref",
        "from_model_name",
        "from_id_ref",
    )
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.method:
                parts.append(rec.method)
            if rec.from_model_name:
                parts.append(f"{rec.from_model_name}:{rec.from_id_ref}")
            if rec.to_model_name:
                parts.append(f"{rec.to_model_name}:{rec.to_id_ref}")
            rec.name = " ".join(parts)

    def action_set_no_match(self):
        self.ensure_one()
        if self.sync_data_transform_id.default_option_no_match:
            self.modification = (
                self.sync_data_transform_id.default_option_no_match
            )
            self.has_no_match = True

    def action_write_modification(self):
        for rec in self:
            if rec.modification and not rec.modification_done:
                str_value = rec.modification
                if rec.depend_ids:
                    for depend_id in rec.depend_ids:
                        if not depend_id.modification_done:
                            depend_id.action_write_modification()
                        str_value = str_value.replace(
                            '"' + depend_id.id_depend_name + '"',
                            str(depend_id.to_id_ref),
                        )
                parsed_values = json.loads(str_value)
                res_class = self.env[rec.to_model_name]

                # Transform value
                for key, value in parsed_values.items():
                    key_field = res_class._fields[key]
                    key_type = key_field.type
                    if key_type in ("many2one", "many2many") and isinstance(
                        value, str
                    ):
                        # Create if not existing, search by rec_name
                        key_class = self.env[key_field.comodel_name]
                        value_transform = key_class.search(
                            [(key_class._rec_name, "=", value)], limit=1
                        )
                        if not value_transform:
                            value_transform = key_class.create(
                                [{key_class._rec_name: value}]
                            )
                        parsed_values[key] = value_transform.id

                if rec.method == "create":
                    to_id_ref = res_class.create(parsed_values)
                    rec.to_id_ref = to_id_ref.id
                elif rec.method == "write":
                    if not rec.to_id_ref:
                        _logger.error(
                            "Cannot write model '%s'",
                            rec.from_model_name,
                        )
                    else:
                        res_class.browse(rec.to_id_ref).write(parsed_values)
                rec.modification_done = True
