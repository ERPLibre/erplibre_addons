# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
from odoo import fields, models

from ..tools.sms_api_erplibre import SmsApiErplibre


class ResCompany(models.Model):
    _inherit = "res.company"

    #: Le champ est defini par le module coeur `sms_twilio`
    #: (models/res_company.py lignes 12-19) ; on ne fait qu'ajouter une valeur.
    sms_provider = fields.Selection(
        selection_add=[("erplibre", "Passerelle mobile ERPLibre")],
        ondelete={"erplibre": "set default"},
    )

    def _get_sms_api_class(self):
        self.ensure_one()
        if self.sms_provider == "erplibre":
            return SmsApiErplibre
        return super()._get_sms_api_class()
