# ERPLibre — signature de l'utilisateur

`base_user_signature` (OCA) ajoute à `res.users` une image de signature,
dessinée ou importée dans **Mon profil**, sous « Signature e-mail ». Le widget
`signature` d'Odoo offre trois modes : dessiner, signature automatique à partir
du nom, ou charger une image (PNG, JPEG, SVG). L'image chargée est redessinée
dans un canevas et enregistrée en PNG ; c'est d'ailleurs la seule voie pour un
SVG, qu'Odoo 18 refuse brut à qui n'est pas administrateur.

Tel quel, tout utilisateur interne y lit la signature d'un autre.

## Ce que le module fait

| | |
|---|---|
| Lecture et écriture | Réservées au **propriétaire** (par `SELF_READABLE_FIELDS` et `SELF_WRITEABLE_FIELDS`) et aux **administrateurs**. Un rapport qui imprime la signature la lit en superutilisateur. |
| Mon profil | Le libellé « Signature » reste affiché pour chacun : le cœur lève la restriction de groupes des seuls nœuds `field` de la vue des préférences, et un `label` en hérite. |
| Administration | Le bouton d'effacement du formulaire des utilisateurs suit le champ : un gestionnaire des droits d'accès qui n'est pas administrateur ne le voit pas, faute de pouvoir écrire la signature d'un autre. |

Le portail, qui n'a pas accès à **Mon profil**, est couvert par
`erplibre_user_signature_portal`.
