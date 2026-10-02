# ERPLibre — répondeur de la ligne cellulaire

La boîte vocale de l'opérateur prend l'appel au bout d'une trentaine de
secondes, et ce qu'elle garde n'est consultable qu'en l'appelant : **aucune
commande AT ne liste ses messages**, et le modem n'a aucun stockage amovible.
Répondre avant elle est la seule façon d'avoir un historique.

## La course

Une sonnerie complète dure **six secondes** — deux de courant, quatre de
silence. La boîte vocale de l'opérateur répond vers **trente**. Le nombre de
sonneries est donc borné à **cinq** : au-delà, le répondeur ne décrocherait
jamais, et la panne se lirait « il ne marche pas » sans autre indice.

Défaut : quatre sonneries.

## Qui décide

| | |
|---|---|
| Odoo répond | Ses réglages font autorité — sonneries, durée, annonce. |
| Odoo se tait | Ceux du disque tiennent, écrits par la TUI sous `private/`. |

C'est précisément pendant une panne du serveur que quelqu'un laisse un
message : la ligne ne doit pas devenir muette avec lui.

## Éteint par défaut

Décrocher à la place de quelqu'un s'entend. Une machine qui répond sur une
ligne dont le propriétaire ignore qu'elle en a une est une surprise
désagréable.

## Ce que le module fait

- Rapproche chaque message de sa fiche **par les chiffres du numéro** — la
  seule comparaison qui survive au formatage.
- Prévient les personnes désignées : un répondeur dont personne n'apprend
  qu'il a reçu quelque chose ne vaut pas mieux que pas de répondeur.
- Marque un message écouté ou non, ouvre ou prépare la fiche du contact.
- Le numéro porte le widget `phone`, que `voip_oca` détourne : cliquer dessus
  rappelle par le softphone.

## Les deux routes

Signées HMAC, horodatées, avec un jeton à usage unique — la même protection
que la passerelle SMS, et pour la même raison : le service n'a pas de session
Odoo.

```
POST /erplibre_repondeur/reglages   → sonneries, durée, annonce
POST /erplibre_repondeur/message    → dépose un enregistrement
```

Le secret vient de l'environnement du processus, jamais de la base ni du dépôt :

```
ERPLIBRE_SMS_HMAC_SECRET   partagé avec la passerelle SMS
ERPLIBRE_ODOO_URL          côté service, pour qu'il sache où appeler
```

Un message qui ne monte pas **reste sur disque avec son compagnon**, et le
démarrage suivant le rattrape. La référence évite le doublon quand une réponse
s'est perdue en chemin.

## Essais

```bash
./test.sh -d test_rep -i erplibre_repondeur --stop-after-init \
  --log-level=test --db-filter test_rep
```
