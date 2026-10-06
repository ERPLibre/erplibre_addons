# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models

from ..tools import signature


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    erplibre_sms_provider = fields.Selection(
        related="company_id.erplibre_sms_provider",
        readonly=False,
        string="Fournisseur SMS ERPLibre",
        help="Qui envoie les SMS de cette societe. « Aucun » laisse le choix "
             "au coeur d'Odoo et a ses connecteurs.",
    )
    erplibre_gateway_id = fields.Many2one(
        "erplibre.sms.gateway",
        "Passerelle mobile",
        related="company_id.erplibre_gateway_id",
        readonly=False,
        help="Materiel qui envoie les SMS. Vide = la premiere passerelle "
             "active par sequence, ce qui suffit tant qu'il n'y en a qu'une.",
    )
    erplibre_sms_daily_quota = fields.Integer(
        "Quota quotidien de SMS",
        config_parameter="erplibre_mobile_gateway.daily_quota",
        help="0 = pas de quota. Protege contre une boucle d'automatisation qui "
             "viderait le forfait en une nuit.",
    )
    erplibre_sms_secret_present = fields.Boolean(
        "Secret HMAC configure", compute="_compute_erplibre_sms_secret_present",
        help="Le secret est lu dans l'environnement du processus Odoo, jamais en "
             "base : le code de ce module est publie sous AGPL-3.",
    )

    @api.depends_context("uid")
    def _compute_erplibre_sms_secret_present(self):
        try:
            signature.get_hmac_secret()
            has_secret = True
        except signature.MissingSecret:
            has_secret = False
        for record in self:
            record.erplibre_sms_secret_present = has_secret
