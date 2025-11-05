from odoo import _, api, exceptions, fields, models, tools


class DevopsLogMakefileTarget(models.Model):
    _name = "devops.log.makefile.target"
    _description = "Log makefile target (to call command) for a workspace"

    name = fields.Char()

    devops_workspace_id = fields.Many2one(
        comodel_name="devops.workspace",
        string="Devops Workspace",
    )

    def action_launch_target(self):
        for rec in self:
            with rec.devops_workspace_id.devops_create_exec_bundle(
                "Launch target"
            ) as rec_ws:
                exec_id = rec_ws.execute(
                    cmd=f"make {rec.name}", to_instance=True
                )
