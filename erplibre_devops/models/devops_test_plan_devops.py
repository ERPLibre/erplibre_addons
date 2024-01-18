import logging

from odoo import _, api, exceptions, fields, models

_logger = logging.getLogger(__name__)


class DevopsTestPlanDevops(models.Model):
    _name = "devops.test.plan.devops"
    _description = "test plan devops -> choose devops.test.exec to create"

    name = fields.Char()
