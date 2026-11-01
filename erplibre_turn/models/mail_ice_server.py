# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Liste ICE construite à partir d'un secret partagé avec coturn.

coturn, en mode `use-auth-secret`, accepte tout nom d'utilisateur de la
forme `<expiration>:<identifiant>` dont le mot de passe vaut
`base64(HMAC-SHA1(secret, nom))`, tant que l'horodatage Unix
`<expiration>` n'est pas dépassé. Odoo calcule ce couple à chaque entrée
dans un appel ; le secret ne quitte jamais le serveur.
"""

import base64
import hashlib
import hmac
import logging
import time

from odoo import models

_logger = logging.getLogger(__name__)

PARAM_SECRET = "erplibre_turn.secret"
PARAM_URLS = "erplibre_turn.urls"
PARAM_TTL = "erplibre_turn.ttl_hours"
DEFAULT_TTL_HOURS = 24
# Firefox avertit au-delà de cinq serveurs ICE ; mail applique la même
# borne à ses lignes (`search(limit=5)`).
MAX_ICE_SERVERS = 5


def turn_credential(secret, username):
    """Rend le mot de passe REST de coturn pour `username`.

    `base64(HMAC-SHA1(secret, username))`, en texte ASCII. Le module
    `hmac` de la bibliothèque standard suffit : coturn n'attend ni sel ni
    autre encodage.
    """
    digest = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def ttl_hours(raw):
    """Rend la durée de vie en heures lue dans le paramètre, au moins 1.

    Une valeur absente ou illisible rend la durée par défaut ; zéro ou une
    valeur négative rend 1, pour qu'un identifiant ne naisse jamais expiré.
    `get_param` rend `False` pour un paramètre absent, et `int(False)`
    vaudrait 0 : ce cas est écarté avant la conversion.
    """
    if raw is None or raw is False or raw == "":
        return DEFAULT_TTL_HOURS
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_TTL_HOURS
    return max(hours, 1)


class MailIceServer(models.Model):
    _inherit = "mail.ice.server"

    def _erplibre_turn_userid(self):
        """Rend la partie identifiant du nom d'utilisateur TURN.

        `odoo-u<id>` pour un utilisateur, `odoo-guest` pour l'utilisateur
        public (invités d'un lien d'appel). Jamais l'identifiant de
        connexion : le nom apparaît dans le journal de coturn.
        """
        user = self.env.user
        if user._is_public():
            return "odoo-guest"
        return f"odoo-u{user.id}"

    def _erplibre_turn_servers(self, secret, urls, hours):
        """Rend une entrée RTCIceServer par URL.

        Les URL `stun:` ne portent ni nom ni mot de passe ; toutes les
        autres portent le même couple, valide `hours` heures à partir de
        maintenant.
        """
        expiry = int(time.time()) + hours * 3600
        username = f"{expiry}:{self._erplibre_turn_userid()}"
        credential = turn_credential(secret, username)
        servers = []
        for url in urls:
            server = {"urls": url}
            if not url.lower().startswith("stun:"):
                server["username"] = username
                server["credential"] = credential
            servers.append(server)
        return servers

    def _get_ice_servers(self):
        """Rend la liste ICE signée par le secret, puis les lignes locales.

        Twilio activé, secret ou liste d'URL vide : rend exactement ce que
        rend mail, pour que la configuration d'Odoo garde la main et qu'une
        base sans réglage rende `[]`. Sinon, les entrées du module viennent
        en premier, entières ; les lignes `mail.ice.server` suivent tant que
        le total ne dépasse pas cinq. Les lignes écartées, ou une liste du
        module déjà plus longue que cinq, laissent un avertissement.
        """
        params = self.env["ir.config_parameter"].sudo()
        if params.get_param("mail.use_twilio_rtc_servers"):
            return super()._get_ice_servers()
        secret = params.get_param(PARAM_SECRET) or ""
        raw_urls = params.get_param(PARAM_URLS) or ""
        urls = [line.strip() for line in raw_urls.splitlines()]
        urls = [url for url in urls if url]
        if not secret or not urls:
            return super()._get_ice_servers()
        hours = ttl_hours(params.get_param(PARAM_TTL))
        servers = self._erplibre_turn_servers(secret, urls, hours)
        if len(servers) > MAX_ICE_SERVERS:
            _logger.warning(
                "%s holds %d URLs, more than the %d ICE servers Firefox"
                " accepts without warning",
                PARAM_URLS,
                len(servers),
                MAX_ICE_SERVERS,
            )
        local = self._get_local_ice_servers()
        room = max(MAX_ICE_SERVERS - len(servers), 0)
        if len(local) > room:
            _logger.warning(
                "%d mail.ice.server row(s) dropped: %d entries from %s"
                " leave room for %d of %d",
                len(local) - room,
                len(servers),
                PARAM_URLS,
                room,
                MAX_ICE_SERVERS,
            )
        return servers + local[:room]
