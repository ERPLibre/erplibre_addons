from odoo import fields, models


class SyncDataExecCronLog(models.Model):
    _name = "sync.data.exec.cron.log"
    _description = "Log of cron execution"

    name = fields.Char()

    error_msg = fields.Text()
