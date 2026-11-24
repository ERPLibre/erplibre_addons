# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Passage à 1.6 : le booléen `erplibre_quiet_while_online` des appareils
de notification devient le mode `erplibre_browser_mode`."""

from odoo.tools.sql import column_exists


def migrate(cr, version):
    """Donne à chaque appareil le mode `quiet` quand sa colonne
    `erplibre_quiet_while_online` (1.5) est vraie, `ring` sinon, puis
    supprime cette colonne, que l'ORM de 1.6 ne connaît plus. Sans la
    colonne, ne fait rien. La version de la charge reste celle que le
    chargement a posée (1, la valeur par défaut) : ces appareils ont été
    marqués par une application 1.5."""
    if not column_exists(
        cr, "mail_push_device", "erplibre_quiet_while_online"
    ):
        return
    cr.execute(
        """
        UPDATE mail_push_device
           SET erplibre_browser_mode = CASE
                   WHEN erplibre_quiet_while_online THEN 'quiet'
                   ELSE 'ring'
               END
        """
    )
    cr.execute(
        "ALTER TABLE mail_push_device"
        " DROP COLUMN IF EXISTS erplibre_quiet_while_online"
    )
