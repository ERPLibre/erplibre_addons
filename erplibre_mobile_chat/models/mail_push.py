# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""File d'attente des notifications : les lignes des appareils de
l'application passent par l'expéditeur du module."""

from odoo import api, models
from odoo.osv import expression

from ..tools import app_push

APP_ROWS = [("mail_push_device_id.erplibre_app", "=", True)]


class MailPush(models.Model):
    _inherit = "mail.push"

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        # Sous ce contexte, le cron d'Odoo ne voit ni n'envoie les lignes des
        # appareils de l'application, que ce module envoie lui-même.
        if self.env.context.get("erplibre_skip_app_devices"):
            domain = expression.AND(
                [domain, [("mail_push_device_id.erplibre_app", "=", False)]]
            )
        return super()._search(domain, offset=offset, limit=limit, order=order)

    @api.model
    def _push_notification_to_endpoint(self, batch_size=50):
        """Prend jusqu'à `batch_size` lignes des appareils de l'application,
        les supprime et confie leurs envois à app_push.schedule, puis laisse
        Odoo traiter les autres lignes, sous `erplibre_skip_app_devices`.

        Sans clés VAPID, les lignes restent, comme chez Odoo, pour un
        prochain passage. Les envois partent après la validation de la
        transaction du cron : un appareil disparu est alors supprimé dans un
        curseur neuf sans attendre les lignes que cette transaction a
        supprimées. Le cron est relancé tant qu'il reste des lignes de
        l'application.
        """
        rows = self.browse()
        if app_push.vapid_keys_present(self.env):
            rows = self.sudo().search_fetch(
                APP_ROWS, ["mail_push_device_id", "payload"], limit=batch_size
            )
        if rows:
            items = [(row.mail_push_device_id, row.payload) for row in rows]
            app_push.schedule(self.env, items)
            rows.unlink()
            if self.sudo().search_count(APP_ROWS):
                self.env.ref("mail.ir_cron_web_push_notification")._trigger()
        return super(
            MailPush, self.with_context(erplibre_skip_app_devices=True)
        )._push_notification_to_endpoint(batch_size=batch_size)
