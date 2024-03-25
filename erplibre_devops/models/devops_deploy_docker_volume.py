from odoo import _, api, fields, models


class DevopsDeployDockerVolume(models.Model):
    _name = "devops.deploy.docker.volume"
    _description = "devops_deploy_docker_volume"

    name = fields.Char()

    system_id = fields.Many2one(
        comodel_name="devops.system",
        string="System",
    )
