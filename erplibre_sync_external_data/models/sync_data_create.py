from odoo import api, fields, models


class SyncDataCreate(models.Model):
    _name = "sync.data.create"
    _description = "Create data from sync.data.exec"

    name = fields.Char(compute="_compute_name")

    res_model = fields.Char(
        "Related Document Model Name", required=True, index=True
    )

    res_id = fields.Many2oneReference(
        "Related Document ID",
        index=True,
        help="Id of the followed resource",
        model_field="res_model",
    )

    sync_data_exec_id = fields.Many2one(
        comodel_name="sync.data.exec", string="Sync Data Exec"
    )

    @api.depends("res_model", "res_id")
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.res_model} - {rec.res_id}"
