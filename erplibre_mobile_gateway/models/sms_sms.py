# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
from odoo import models

from ..tools.sms_api_erplibre import SmsApiErplibre


class SmsSms(models.Model):
    _inherit = "sms.sms"

    def _split_by_api(self):
        """Route vers la passerelle les SMS des societes qui l'ont choisie.

        Meme decoupage que `sms_twilio` (models/sms_sms.py lignes 57-72) : on
        groupe par societe, on cede notre API pour celles qui sont sur
        `erplibre`, et on delegue le reste au `super()`.
        """
        todo_via_super = self.env["sms.sms"]
        by_company = {}
        for sms in self:
            by_company.setdefault(sms._get_sms_company(), self.env["sms.sms"])
            by_company[sms._get_sms_company()] |= sms

        for company, sms_records in by_company.items():
            if company.sms_provider == "erplibre":
                sms_api = SmsApiErplibre(self.env)
                sms_api._set_company(company)
                yield sms_api, sms_records
            else:
                todo_via_super |= sms_records

        if todo_via_super:
            yield from super(SmsSms, todo_via_super)._split_by_api()
