# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
import logging
from datetime import timedelta

from odoo import api, fields, models

from ..tools import signature

_logger = logging.getLogger(__name__)


class ErplibreSmsNonce(models.Model):
    """Nonces deja vus, pour rejeter les rejeus.

    Une signature HMAC valide prouve l'origine, pas la fraicheur : sans nonce,
    un rapport intercepte peut etre rejoue indefiniment. La fenetre temporelle
    borne la taille de cette table ; le nonce empeche le rejeu a l'interieur de
    la fenetre.
    """

    _name = "erplibre.sms.nonce"
    _description = "Nonce de la passerelle SMS"
    _rec_name = "nonce"

    nonce = fields.Char("Nonce", required=True, index=True)
    device_id = fields.Char("Appareil", index=True)
    seen_at = fields.Datetime("Vu le", required=True, default=fields.Datetime.now, index=True)

    _sql_constraints = [
        ("nonce_unique", "unique(nonce)", "Nonce deja utilise."),
    ]

    @api.model
    def _consume(self, nonce, device_id=None):
        """Retourne True si le nonce est neuf, False s'il a deja servi."""
        if not nonce:
            return False
        # Pre-verification pour le cas courant : evite de faire echouer une
        # requete SQL, ce qui journalise une erreur a chaque rejeu.
        if self.sudo().search_count([("nonce", "=", nonce)], limit=1):
            _logger.warning("erplibre_mobile_gateway: nonce rejoue depuis %s", device_id)
            return False
        # Le savepoint reste la vraie garde : deux requetes concurrentes
        # pourraient passer la pre-verification en meme temps, et seule la
        # contrainte d'unicite les separe.
        try:
            with self.env.cr.savepoint():
                self.create({"nonce": nonce, "device_id": device_id})
        except Exception:  # noqa: BLE001 - violation de contrainte d'unicite
            _logger.warning("erplibre_mobile_gateway: nonce concurrent depuis %s", device_id)
            return False
        return True

    @api.autovacuum
    def _gc_nonces(self):
        # Un nonce n'a besoin de survivre QUE le temps de la fenetre de
        # fraicheur : au-dela, l'horodatage rejette deja la requete. Garder
        # deux jours ferait 2880 lignes par appareil et par jour avec une
        # interrogation par minute, pour aucun gain de securite.
        limit = fields.Datetime.now() - timedelta(seconds=signature.MAX_CLOCK_SKEW * 4)
        stale = self.search([("seen_at", "<", limit)])
        count = len(stale)
        stale.unlink()
        if count:
            _logger.info("erplibre_mobile_gateway: %s nonces purges", count)
