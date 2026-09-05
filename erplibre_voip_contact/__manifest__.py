# Part of TechnoLibre. See LICENSE file for full copyright and licensing details.
{
    "name": "ERPLibre — appels VoIP et fiches contact",
    "summary": "Rapprocher un appel VoIP de sa fiche, son historique et son dossier",
    "description": """
Appels VoIP relies aux fiches contact
=====================================

``voip_oca`` rapproche un appel de sa fiche par EGALITE DE CHAINE sur ``phone``
ou ``mobile``. Un numero presente « 15145550142 » et une fiche qui porte
« +1 514-555-0142 » designent la meme personne, et l'egalite les separe.

La consequence n'est pas cosmetique : l'appel s'affiche « No contact info », le
bouton qui ouvre la fiche — conditionne a la presence du contact — n'apparait
pas, et RAPPELER depuis cet appel part sans numero, le softphone se rabattant
sur le mobile d'une fiche absente. La creation de l'appel echoue alors sur un
champ obligatoire vide.

Ce module :

* rapproche par les CHIFFRES, la seule comparaison qui survive au formatage,
  avant de laisser ``voip_oca`` faire son essai d'origine ;
* rattache a l'installation les appels deja enregistres, sans quoi l'historique
  resterait vide jusqu'au prochain appel ;
* montre dans le panneau d'appel les echanges precedents avec le meme
  correspondant, contact d'abord et numero a defaut ;
* offre de creer la fiche quand le numero est inconnu, puis rattache l'appel en
  cours a la fiche qui vient d'etre creee.
""",
    "author": "TechnoLibre",
    "website": "https://erplibre.ca",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": [
        "voip_oca",
        # Le rapprochement par les chiffres est celui de `phone.common`, que
        # `erplibre_mobile_gateway` corrige pour qu'il survive aux tirets et
        # aux parentheses. En dependre plutot que de le recopier evite deux
        # rapprochements qui divergeraient.
        "erplibre_mobile_gateway",
    ],
    "assets": {
        "web.assets_backend": [
            "erplibre_voip_contact/static/src/*.js",
            "erplibre_voip_contact/static/src/*.xml",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
