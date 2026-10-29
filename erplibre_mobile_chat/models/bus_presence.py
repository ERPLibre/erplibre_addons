# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Présence des navigateurs d'un utilisateur, à côté de celle d'Odoo, qui
compte aussi le bus de l'application."""

from datetime import timedelta

from odoo import api, fields, models, tools
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY


class BusPresence(models.Model):
    _inherit = "bus.presence"

    erplibre_browser_poll = fields.Datetime(
        string="Last Browser Poll",
        groups="base.group_system",
        help="Last presence update of a browser of this user; the bus of the"
        " ERPLibre mobile app does not count.",
    )
    erplibre_browser_presence = fields.Datetime(
        string="Last Browser Presence",
        groups="base.group_system",
        help="Last activity in a browser of this user; the bus of the"
        " ERPLibre mobile app does not count.",
    )
    erplibre_browser_user_id = fields.Many2one(
        "res.users",
        string="Browser User",
        groups="base.group_system",
        ondelete="cascade",
        help="User whose browser wrote the two browser fields; a row moved"
        " to another user keeps it.",
    )

    @api.model
    def _erplibre_update_browser_presence(self, inactivity_period):
        """Écrit, comme update_presence d'Odoo, le dernier sondage (now) et
        la dernière activité (now − `inactivity_period` millisecondes, 0
        au moins) d'un navigateur de l'utilisateur de l'environnement
        (`env.uid`, que sudo garde) dans sa présence existante, avec cet
        utilisateur (`erplibre_browser_user_id`), puis valide.

        Privée : aucun appel RPC ne l'atteint, et l'utilisateur n'est jamais
        un paramètre. Les trois champs ne sont lisibles et modifiables que
        par l'administrateur ; l'appelant passe par sudo. Un utilisateur
        peut changer le `user_id` d'une présence (Odoo lui en donne
        l'écriture) ; `erplibre_browser_user_id`, lui, reste celui du
        navigateur qui a écrit.

        Une erreur de concurrence (deux onglets en même temps) annule la
        transaction et est ignorée, comme chez Odoo : la présence n'est pas
        essentielle. Sans ligne de présence, rien n'est écrit : celle
        d'Odoo, écrite juste avant, a alors cédé à la même concurrence.
        """
        inactivity_period = max(0, int(inactivity_period))
        try:
            with tools.mute_logger("odoo.sql_db"):
                presence = self.search([("user_id", "=", self.env.uid)])
                if presence:
                    now = fields.Datetime.now()
                    presence.write(
                        {
                            "erplibre_browser_user_id": self.env.uid,
                            "erplibre_browser_poll": now,
                            "erplibre_browser_presence": now
                            - timedelta(milliseconds=inactivity_period),
                        }
                    )
                self.env.cr.commit()
        except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
            return self.env.cr.rollback()
