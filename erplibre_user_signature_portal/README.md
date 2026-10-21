# ERPLibre — signature de l'utilisateur au portail

Un utilisateur du portail n'a pas accès à **Mon profil** du back-office, où
`erplibre_user_signature` place la signature. Ce module l'ajoute à la page des
coordonnées du portail, `/my/account`.

## Ce que le module fait

| | |
|---|---|
| Affichage | Une section « Signature » sous le formulaire des coordonnées montre la signature actuelle. |
| Signer | Le bouton ouvre le composant de signature du portail : dessin, signature automatique à partir du nom, ou image importée. Le navigateur l'enregistre en PNG. |
| Effacer | Un formulaire `POST` protégé par le jeton CSRF. |
| Portée | Chaque route écrit par `request.env.user` : `res.users.write` n'élève ses droits que pour l'utilisateur lui-même, ce qui interdit de viser la signature d'un autre. |

La section vit hors du formulaire des coordonnées : enregistrer ses
coordonnées ne touche pas à la signature.

## Routes

| Route | Type | Rôle |
|---|---|---|
| `/my/signature` | JSON | Enregistre l'image en base64 ; rend `error` si elle est vide ou illisible. |
| `/my/signature/delete` | HTTP `POST` | Efface la signature, puis revient à `/my/account`. |
