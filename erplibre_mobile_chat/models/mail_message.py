# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""L'identifiant client d'un message publié depuis l'application mobile,
l'empreinte de son corps, le favori idempotent, le niveau du module et la
notification « traité » vers les appareils de l'application."""

import hashlib
import json
import logging

from odoo import api, fields, models
from odoo.addons.mail.tools.discuss import Store
from odoo.tools.sql import index_exists

from ..tools import app_push

_logger = logging.getLogger(__name__)

# Au-delà de ce nombre de fils, la notification « traité » porte
# `threads: null` : l'application revoit alors toute sa boîte.
INBOX_DONE_MAX_THREADS = 40


def erplibre_ensure_unique_uuid_index(cr, table, index, columns):
    """Crée l'index unique partiel (columns) sur les lignes dont
    erplibre_client_uuid est renseigné, s'il n'existe pas.

    Une base montée avec une version sans l'index peut porter des doublons
    qui feraient échouer la création, donc la mise à jour du module : avant
    de créer l'index, tout doublon d'un groupe garde son identifiant pour la
    ligne de plus petit id et le perd pour les autres (la ligne reste, seul
    le dédoublonnage futur la perd). Sans effet quand l'index existe déjà.
    """
    if index_exists(cr, index):
        return
    cols = ", ".join(columns)
    cr.execute(
        f"UPDATE {table} SET erplibre_client_uuid = NULL"
        f" WHERE id IN (SELECT id FROM (SELECT id, ROW_NUMBER() OVER"
        f" (PARTITION BY {cols} ORDER BY id) AS rank FROM {table}"
        f" WHERE erplibre_client_uuid IS NOT NULL) ranked WHERE rank > 1)"
    )
    if cr.rowcount:
        _logger.warning(
            "%s: %s duplicate erplibre_client_uuid cleared before indexing",
            table,
            cr.rowcount,
        )
    cr.execute(
        f"CREATE UNIQUE INDEX {index} ON {table} ({cols})"
        f" WHERE erplibre_client_uuid IS NOT NULL"
    )


class MailMessage(models.Model):
    _inherit = "mail.message"

    erplibre_client_uuid = fields.Char(
        string="Client UUID",
        index="btree_not_null",
        copy=False,
        readonly=True,
        help="Identifiant généré par l'application mobile ; un renvoi du"
        " même identifiant par le même auteur sur le même fil ne crée"
        " pas de second message.",
    )

    erplibre_body_fingerprint = fields.Char(
        string="Body Fingerprint",
        compute="_compute_erplibre_body_fingerprint",
        help="SHA-256 hexadécimal du corps HTML tel que le rend Store,"
        " encodé en UTF-8 ; la modification gardée le compare à"
        " l'empreinte attendue par l'application.",
    )

    erplibre_chat_level = fields.Selection(
        [("1.4", "1.4"), ("1.5", "1.5")],
        string="ERPLibre Chat Level",
        compute="_compute_erplibre_chat_level",
        help="Niveau du module : la plus haute clé de la sélection. Un"
        " niveau suivant ajoute sa clé en fin de sélection.",
    )

    @api.depends("body")
    def _compute_erplibre_body_fingerprint(self):
        # Le champ, non stocké et sans groupe, figure dans fields_get pour
        # tout utilisateur interne : sa présence signale aussi le niveau
        # 1.3 du module, qui offre la modification gardée.
        for message in self:
            message.erplibre_body_fingerprint = hashlib.sha256(
                str(message.body or "").encode()
            ).hexdigest()

    def _compute_erplibre_chat_level(self):
        # La sélection, non stockée et sans groupe, figure dans fields_get
        # pour tout utilisateur interne, avec ses clés : l'application lit
        # le niveau dans `selection` sans lire d'enregistrement.
        # Un niveau s'ajoute en fin de sélection : la dernière clé est la
        # plus haute.
        level = self._fields["erplibre_chat_level"].selection[-1][0]
        for message in self:
            message.erplibre_chat_level = level

    def erplibre_set_starred(self, starred):
        """Met les messages en favori (`starred` vrai) ou les en retire pour
        l'utilisateur courant, et rend leur état au format de
        `toggle_message_starred`.

        Contrairement à la bascule d'Odoo, un renvoi ne défait rien : seuls
        les messages dont l'état diffère changent, et le bus
        `mail.message/toggle_star` de l'utilisateur ne porte que ceux-là ;
        aucun envoi quand rien ne change. Comme chez Odoo, tout message
        lisible peut être mis en favori : un message illisible lève
        AccessError.
        """
        starred = bool(starred)
        self.check_access("read")
        changed = self.filtered(lambda message: message.starred != starred)
        if changed:
            partner = self.env.user.partner_id
            if starred:
                partner.starred_message_ids |= changed
            else:
                partner.starred_message_ids -= changed
            self.env.user._bus_send(
                "mail.message/toggle_star",
                {"message_ids": changed.ids, "starred": starred},
            )
        return Store(self, {"starred": starred}).get_result()

    def _erplibre_unread_for_me(self, message_ids=None):
        """Rend, sous sudo, les messages dont le partenaire courant a une
        notification de boîte non lue, parmi `message_ids` quand il est
        donné : ceux que set_message_done et mark_all_as_read marquent."""
        domain = [
            ("res_partner_id", "=", self.env.user.partner_id.id),
            ("is_read", "=", False),
        ]
        if message_ids is not None:
            domain.append(("mail_message_id", "in", message_ids))
        # sudo: mail.notification - comme Odoo, les notifications du
        # partenaire courant seulement.
        return (
            self.env["mail.notification"]
            .sudo()
            .search_fetch(domain, ["mail_message_id"])
            .mail_message_id
        )

    def _erplibre_send_inbox_done(self):
        """Envoie aux appareils de l'application du partenaire courant la
        notification « traité » des fils de ces messages hors des canaux :
        `{"erplibre": {"v", "type": "inbox_done", "threads": [[modèle,
        id], …]}}`, triés, ou `threads` à null au-delà de
        INBOX_DONE_MAX_THREADS fils. Rien quand aucun fil ne reste : un
        canal a sa notification « lu »."""
        threads = sorted(
            {
                (message.model, message.res_id)
                for message in self
                if message.model
                and message.res_id
                and message.model != "discuss.channel"
            }
        )
        if not threads:
            return
        devices = self.env["mail.push.device"]._erplibre_app_devices(
            self.env.user.partner_id.ids
        )
        if not devices:
            return
        if len(threads) > INBOX_DONE_MAX_THREADS:
            threads = None
        else:
            threads = [list(thread) for thread in threads]
        payload = json.dumps(
            {
                "erplibre": {
                    "v": app_push.PAYLOAD_VERSION,
                    "type": "inbox_done",
                    "threads": threads,
                }
            }
        )
        app_push.schedule(self.env, [(device, payload) for device in devices])

    def set_message_done(self):
        """Comme Odoo, puis envoie la notification « traité » des messages
        que l'appel a marqués pour le partenaire courant."""
        done = self._erplibre_unread_for_me(self.ids)
        result = super().set_message_done()
        done._erplibre_send_inbox_done()
        return result

    @api.model
    def mark_all_as_read(self, domain=None):
        """Comme Odoo, puis envoie la notification « traité » des messages
        marqués. Avec `domain`, Odoo passe par set_message_done, qui
        l'envoie."""
        if domain:
            return super().mark_all_as_read(domain=domain)
        done = self._erplibre_unread_for_me()
        result = super().mark_all_as_read(domain=domain)
        done._erplibre_send_inbox_done()
        return result

    def init(self):
        # Garantie du dédoublonnage de message_post (voir
        # erplibre_lock_uuid : le verrou sérialise, cet index garantit).
        # L'index btree_not_null du champ reste pour la recherche par seul
        # identifiant.
        super().init()
        erplibre_ensure_unique_uuid_index(
            self.env.cr,
            "mail_message",
            "mail_message_erplibre_client_uuid_uniq",
            ["author_id", "model", "res_id", "erplibre_client_uuid"],
        )
