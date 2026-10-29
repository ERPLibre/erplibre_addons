# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Appareils de l'application mobile parmi les appareils de notification
d'Odoo."""

from odoo import api, fields, models
from odoo.osv import expression

# Champs que la route /erplibre_mobile_chat/push/device renseigne et
# qu'un changement de partenaire efface.
APP_FIELDS = {
    "erplibre_app": False,
    "erplibre_quiet_while_online": False,
    "erplibre_session_hash": False,
}


class MailPushDevice(models.Model):
    _inherit = "mail.push.device"

    erplibre_app = fields.Boolean(
        string="ERPLibre App",
        copy=False,
        help="The ERPLibre mobile app receives the notifications of this"
        " device: they carry the message id and the channel type, and"
        " Odoo's own sending skips it.",
    )
    erplibre_quiet_while_online = fields.Boolean(
        string="Quiet While a Browser Is Online",
        copy=False,
        help="No message notification reaches this device while a browser"
        " of its user is online.",
    )
    erplibre_session_hash = fields.Char(
        string="App Session Hash",
        copy=False,
        help="SHA-256 (hexadecimal) of the id of the session that marked"
        " this device as the app's.",
    )

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        # Sous ce contexte, posé par _notify_thread_by_web_push et le cron
        # de mail.push de ce module autour de leur super(), le code d'Odoo
        # ne voit que les appareils hors de l'application.
        if self.env.context.get("erplibre_skip_app_devices"):
            domain = expression.AND([domain, [("erplibre_app", "=", False)]])
        return super()._search(domain, offset=offset, limit=limit, order=order)

    @api.model
    def register_devices(self, **kw):
        """Comme Odoo, puis efface la marque de l'application quand
        l'enregistrement passe le point de terminaison à un autre
        partenaire : la marque appartient au partenaire qui l'a posée."""
        endpoint = kw.get("previousEndpoint", kw.get("endpoint"))
        device = self.sudo().search([("endpoint", "=", endpoint)], limit=1)
        partner = device.partner_id
        result = super().register_devices(**kw)
        device = device.exists()
        if device and device.partner_id != partner and device.erplibre_app:
            device.write(APP_FIELDS)
        return result

    @api.model
    def _erplibre_app_devices(self, partner_ids):
        """Rend, sous sudo, les appareils de l'application des partenaires
        `partner_ids`, quel que soit le contexte de l'appelant."""
        return (
            self.sudo()
            .with_context(erplibre_skip_app_devices=False)
            .search(
                [
                    ("partner_id", "in", partner_ids),
                    ("erplibre_app", "=", True),
                ]
            )
        )
