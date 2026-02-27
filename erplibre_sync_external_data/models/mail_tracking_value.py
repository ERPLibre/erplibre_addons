import base64
import logging
from datetime import datetime, time
from io import BytesIO

import pytz
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MailTracking(models.Model):
    _inherit = "mail.tracking.value"

    sync_data_exec_id = fields.Many2one(comodel_name="sync.data.exec")

    res_model = fields.Char(related="mail_message_id.model")

    res_id = fields.Many2oneReference(related="mail_message_id.res_id")

    res_id_integer = fields.Integer(compute="_compute_res_id_integer")

    @api.depends("res_id")
    def _compute_res_id_integer(self):
        for rec in self:
            rec.res_id_integer = rec.res_id
