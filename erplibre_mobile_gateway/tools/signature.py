# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
"""Signature HMAC des messages echanges avec la passerelle.

Le code de ce module est publie (AGPL-3, article 13) : aucun secret ne peut y
figurer, ni dans la base de donnees. Les secrets sont lus dans l'environnement
du processus Odoo, alimente par un `EnvironmentFile` systemd dont les droits
sont 0600.

Pourquoi pas `server_environment` d'OCA : sans le module compagnon
`server_environment_files` et sans `running_env` dans la configuration, le champ
reste editable et la valeur saisie est ecrite dans `res_company.server_env_defaults`,
un champ stocke -- donc dans la base et dans les sauvegardes. Verifie sur ce
depot : ni `server_environment_files` ni `running_env` n'existent.
"""
import hashlib
import hmac
import logging
import os

_logger = logging.getLogger(__name__)

ENV_HMAC_SECRET = "ERPLIBRE_SMS_HMAC_SECRET"

SIGNATURE_HEADER = "X-Erplibre-Signature"
SIGNATURE_PREFIX = "sha256="

#: Age maximal d'un message signe, en secondes. Au-dela, il est rejete meme si
#: la signature est valide : cela borne la fenetre de rejeu.
MAX_CLOCK_SKEW = 300


class MissingSecret(Exception):
    """Leve quand un secret attendu est absent de l'environnement."""


def get_hmac_secret():
    secret = os.environ.get(ENV_HMAC_SECRET)
    if not secret:
        raise MissingSecret(
            f"{ENV_HMAC_SECRET} absent de l'environnement du processus Odoo. "
            "Ajoutez-le a l'EnvironmentFile du service systemd ; ne le mettez "
            "ni dans la base de donnees ni dans le depot."
        )
    return secret.encode("utf-8")


def compute(raw_body):
    """Signature hexadecimale du corps brut, tel qu'il a ete transmis."""
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    return hmac.new(get_hmac_secret(), raw_body, hashlib.sha256).hexdigest()


def verify(raw_body, header_value):
    """Comparaison a temps constant. Retourne True si la signature est valide."""
    if not header_value:
        return False
    expected = compute(raw_body)
    received = header_value[len(SIGNATURE_PREFIX):] if header_value.startswith(SIGNATURE_PREFIX) else header_value
    return hmac.compare_digest(expected, received.strip())
