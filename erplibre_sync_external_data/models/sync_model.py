import base64
import logging
from datetime import datetime, time
from io import BytesIO

import pytz
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SyncModel(models.Model):
    _name = "sync.model"
    _description = (
        "Synchronisation model data to guide the sync and transform."
    )
    _inherit = ["mail.activity.mixin", "mail.thread"]

    name = fields.Char(tracking=True)

    model_name = fields.Char(tracking=True)

    scenario = fields.Char(tracking=True)

    context_name = fields.Char(tracking=True)

    spreadsheet_extraction_metadata = fields.Json()
