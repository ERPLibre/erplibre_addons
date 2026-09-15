from odoo import fields, models


class SyncDataExec(models.Model):
    _inherit = "sync.data.exec"

    file = fields.Binary(string="Fichier", attachment=False)
