# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Les reglages du repondeur dans l'ecran de configuration."""
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    repondeur_actif = fields.Boolean(
        related="company_id.repondeur_actif", readonly=False
    )
    repondeur_sonneries = fields.Integer(
        related="company_id.repondeur_sonneries", readonly=False
    )
    repondeur_duree_max = fields.Integer(
        related="company_id.repondeur_duree_max", readonly=False
    )
    repondeur_annonce = fields.Binary(
        related="company_id.repondeur_annonce", readonly=False
    )
    repondeur_annonce_filename = fields.Char(
        related="company_id.repondeur_annonce_filename", readonly=False
    )
    repondeur_notify_user_ids = fields.Many2many(
        related="company_id.repondeur_notify_user_ids", readonly=False
    )
    operateur_releve_auto = fields.Boolean(
        related="company_id.operateur_releve_auto", readonly=False
    )
    operateur_releve_efface = fields.Boolean(
        related="company_id.operateur_releve_efface", readonly=False
    )
    operateur_releve_demande = fields.Datetime(
        related="company_id.operateur_releve_demande"
    )

    def action_relever_la_messagerie(self):
        """Relaie le bouton vers la societe. Les reglages sont transitoires :
        poser la date ici la perdrait a la fermeture de l'ecran."""
        self.ensure_one()
        return self.company_id.action_relever_la_messagerie()
