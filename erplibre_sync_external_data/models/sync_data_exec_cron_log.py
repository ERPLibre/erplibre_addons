import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SyncDataExecCronLog(models.Model):
    _name = "sync.data.exec.cron.log"
    _description = "Log of cron execution"

    name = fields.Char()

    error_msg = fields.Text()
