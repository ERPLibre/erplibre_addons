# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
from odoo import api, fields, models


class SmsSms(models.Model):
    _inherit = "sms.sms"

    #: Societe au moment de la CREATION du message.
    #:
    #: Le coeur resout la societe a l'ENVOI : `mail_message_id.record_company_id
    #: or self.env.company` (sms_sms.py ligne 173). Un SMS cree sans
    #: `mail.message` -- le compositeur en mode numeros, ou du code qui cree un
    #: `sms.sms` directement -- n'a donc plus de societe quand le cron le
    #: reprend : c'est celle de l'utilisateur du cron qui s'applique, et le SMS
    #: part par le fournisseur d'une autre societe.
    #:
    #: Nom distinct de `record_company_id` du module `sms_twilio`, qui repond au
    #: meme besoin : les deux champs coexistent alors sans se redefinir, et
    #: portent la meme valeur.
    erplibre_company_id = fields.Many2one(
        "res.company", "Societe a la creation", ondelete="set null",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            societe = (vals.get("erplibre_company_id")
                       or vals.get("record_company_id")
                       or self.env.company.id)
            vals["erplibre_company_id"] = societe
            # `sms_twilio` couvre le meme besoin par son propre champ et sa
            # propre surcharge de `_get_sms_company`. Laisser les deux
            # divergerait : celui qui repond est le plus externe, donc l'ordre
            # de chargement des modules, et le meme message partirait par une
            # societe differente d'une base a l'autre. Ils portent donc
            # toujours la meme valeur.
            if "record_company_id" in self._fields:
                vals["record_company_id"] = societe
        return super().create(vals_list)

    def _get_sms_company(self):
        return (self.mail_message_id.record_company_id
                or self.erplibre_company_id
                or super()._get_sms_company())

    def _split_by_api(self):
        """Route vers la passerelle les SMS des societes qui l'ont choisie.

        Groupe par societe, cede notre API pour celles dont le fournisseur est
        un des notres, et delegue le reste au `super()` -- le coeur, ou un
        autre connecteur, garde les siennes.
        """
        todo_via_super = self.env["sms.sms"]
        by_company = {}
        for sms in self:
            company = sms._get_sms_company()
            by_company.setdefault(company, self.env["sms.sms"])
            by_company[company] |= sms

        classes = self.env["res.company"]._erplibre_sms_api_classes()
        for company, sms_records in by_company.items():
            classe = classes.get(company.erplibre_sms_provider)
            if classe:
                sms_api = classe(self.env)
                sms_api._set_company(company)
                yield sms_api, sms_records
            else:
                todo_via_super |= sms_records

        if todo_via_super:
            yield from super(SmsSms, todo_via_super)._split_by_api()
