# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..tools.sms_api_erplibre import SmsApiErplibre


class ResCompany(models.Model):
    _inherit = "res.company"

    erplibre_gateway_id = fields.Many2one(
        "erplibre.sms.gateway",
        "Passerelle mobile",
        ondelete="set null",
        help="Materiel qui envoie les SMS de cette societe : un telephone, un "
             "modem, ou tout autre appareil declare ici. Laisser vide reprend "
             "l'ancien comportement, la premiere passerelle active par "
             "sequence -- suffisant tant qu'il n'y en a qu'une, arbitraire des "
             "qu'il y en a deux.",
    )

    #: Le champ est defini par le module coeur `sms_twilio`
    #: (models/res_company.py lignes 12-19) ; on ne fait qu'ajouter une valeur.
    sms_provider = fields.Selection(
        selection_add=[("erplibre", "Passerelle mobile ERPLibre")],
        ondelete={"erplibre": "set default"},
    )

    @api.constrains("erplibre_gateway_id")
    def _check_erplibre_gateway_company(self):
        """Refuse a la configuration ce que l'envoi refuserait en silence.

        `_for_company` ecarte une passerelle d'une autre societe : sans cette
        contrainte, le choix serait accepte a l'ecran et les SMS echoueraient
        plus tard, loin de la cause.
        """
        for company in self:
            gateway = company.erplibre_gateway_id
            if gateway and gateway.company_id != company:
                raise ValidationError(_(
                    "La passerelle « %(gateway)s » appartient a une autre "
                    "societe. Une passerelle envoie depuis SA carte SIM : "
                    "elle ne se prete pas.", gateway=gateway.display_name,
                ))

    def _get_sms_api_class(self):
        self.ensure_one()
        if self.sms_provider == "erplibre":
            return SmsApiErplibre
        return super()._get_sms_api_class()
