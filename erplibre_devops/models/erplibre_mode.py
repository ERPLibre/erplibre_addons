from odoo import _, api, fields, models


class ErplibreMode(models.Model):
    _name = "erplibre.mode"
    _description = "erplibre_mode"

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )

    mode_env = fields.Many2one(
        comodel_name="erplibre.mode.env",
        required=True,
    )

    mode_exec = fields.Many2one(
        comodel_name="erplibre.mode.exec",
        required=True,
    )

    mode_source = fields.Many2one(
        comodel_name="erplibre.mode.source",
        required=True,
    )

    mode_version_base = fields.Many2one(
        comodel_name="erplibre.mode.version.base",
        required=True,
        help="Support base version communautaire",
    )

    mode_version_erplibre = fields.Many2one(
        comodel_name="erplibre.mode.version.erplibre",
        required=True,
        help=(
            "Dev to improve, test to test, prod ready for production, stage to"
            " use a dev and replace a prod"
        ),
    )

    @api.depends(
        "mode_env",
        "mode_exec",
        "mode_source",
        "mode_version_base",
        "mode_version_erplibre",
    )
    def _compute_name(self):
        for rec in self:
            rec.name = (
                "{"
                f"{rec.mode_env.name} "
                f"{rec.mode_exec.name} "
                f"{rec.mode_source.name} "
                f"{rec.mode_version_base.name} "
                f"{rec.mode_version_erplibre.name}"
                "}"
            )

    def get_mode(
        self,
        mode_env_id,
        mode_exec_id,
        mode_source_id,
        mode_version_base,
        mode_version_erplibre,
    ):
        mode_version_base_id = self.env["erplibre.mode.version.base"].search(
            [("value", "=", mode_version_base)]
        )
        if not mode_version_base_id:
            mode_version_base_id = self.env[
                "erplibre.mode.version.base"
            ].create({"value": mode_version_base, "name": mode_version_base})
        mode_version_erplibre_id = self.env[
            "erplibre.mode.version.erplibre"
        ].search([("value", "=", mode_version_erplibre)])
        if not mode_version_erplibre_id:
            mode_version_erplibre_id = self.env[
                "erplibre.mode.version.erplibre"
            ].create(
                {"value": mode_version_erplibre, "name": mode_version_erplibre}
            )
        mode_id = self.env["erplibre.mode"].search(
            [
                ("mode_env", "=", mode_env_id.id),
                ("mode_exec", "=", mode_exec_id.id),
                ("mode_source", "=", mode_source_id.id),
                ("mode_version_base", "=", mode_version_base_id.id),
                ("mode_version_erplibre", "=", mode_version_erplibre_id.id),
            ],
            limit=1,
        )
        if not mode_id:
            mode_id = self.create(
                [
                    {
                        "mode_env": mode_env_id.id,
                        "mode_exec": mode_exec_id.id,
                        "mode_source": mode_source_id.id,
                        "mode_version_base": mode_version_base_id.id,
                        "mode_version_erplibre": mode_version_erplibre_id.id,
                    }
                ]
            )
        return mode_id
