# ERPLibre — Identifiants TURN temporaires

Odoo remet la liste des serveurs ICE (STUN et TURN) à chaque navigateur qui
entre dans un appel, invités compris. Sans ce module, un relais TURN y figure
avec un compte fixe, en clair, valable tant qu'on ne le change pas, et sans
`turns:` puisque le type d'un `mail.ice.server` n'offre que `stun:` et
`turn:`.

Avec ce module, Odoo calcule pour chaque entrée dans un appel des
identifiants TURN temporaires, selon le mécanisme de secret partagé de coturn
(`use-auth-secret`) :

- nom d'utilisateur `<expiration>:<identifiant>`, où `<expiration>` est
  l'horodatage Unix de maintenant plus la durée réglée ;
- mot de passe `base64(HMAC-SHA1(secret, nom d'utilisateur))`.

L'identifiant vaut `odoo-u<id>` pour un utilisateur et `odoo-guest` pour un
invité d'un lien d'appel ; il n'est jamais l'identifiant de connexion, car il
apparaît dans le journal de coturn. Le secret ne quitte pas le serveur Odoo.

## Paramètres système

| Paramètre | Contenu |
|---|---|
| `erplibre_turn.secret` | secret partagé avec coturn (une ligne `turn_secret` de sa base) |
| `erplibre_turn.urls` | une URL par ligne : `stun:`, `turn:` ou `turns:` |
| `erplibre_turn.ttl_hours` | durée de validité en heures, 24 par défaut, au moins 1 |

Les deux premiers sont écrits par l'outil `todo.py` d'ERPLibre
(`TODO › Deploy › Call infrastructure › Ajouter un serveur Odoo`), qui ajoute
le même secret à coturn. La durée se règle dans Configuration › Discuss,
« Durée des identifiants TURN (heures) », sous la liste des serveurs ICE.

## Liste rendue

- Twilio activé dans les réglages de Discuss : la liste d'Odoo, inchangée.
- Secret ou liste d'URL vide : la liste d'Odoo, inchangée (une base sans
  réglage rend toujours aucun serveur, et le navigateur prend son STUN par
  défaut).
- Sinon : une entrée par URL, les `stun:` sans nom ni mot de passe, puis les
  lignes `mail.ice.server` saisies à la main tant que le total ne dépasse pas
  cinq (Firefox avertit au-delà). Les lignes écartées, ou plus de cinq URL
  dans `erplibre_turn.urls`, laissent un avertissement dans le journal
  d'Odoo.

## Durée de vie

Le navigateur reçoit ses identifiants en entrant dans l'appel et ne les
renouvelle pas pendant l'appel. Un pair qui arrive, ou une connexion
reconstruite, après l'expiration n'obtient plus de relais. La durée par
défaut, 24 heures, couvre les appels ordinaires.

Quand `todo.py` remplace le secret, l'ancien reste valide dans coturn une
durée de vie de plus, le temps que les identifiants déjà remis expirent.

## Retrait

« Retirer un serveur Odoo » efface `erplibre_turn.secret` et
`erplibre_turn.urls` : Odoo rend de nouveau sa propre liste. Le module reste
installé.
