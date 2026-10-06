# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Rattache a leur fiche les appels deja enregistres.

    Sans cette reprise, le module corrigerait l'avenir et laisserait le passe
    non rapproche : l'historique du correspondant resterait vide jusqu'au
    prochain appel, alors que c'est justement ce passe qu'on veut lire au
    moment de decrocher.

    Les appels dont le numero ne designe aucune fiche restent tels quels : le
    rapprochement ne CREE pas de contact, il en trouve un.
    """
    appels = env["voip.call"].search([("partner_id", "=", False)])
    rattaches = 0
    for appel in appels:
        identifiant = appel._partenaire_du_numero(appel.phone_number)
        if identifiant:
            appel.partner_id = identifiant
            rattaches += 1
    _logger.info(
        "erplibre_voip_contact: %s appels sur %s rattaches a une fiche",
        rattaches,
        len(appels),
    )
