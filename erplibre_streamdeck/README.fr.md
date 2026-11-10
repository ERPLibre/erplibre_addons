

# ERPLibre — Stream Deck

L'inventaire des Stream Deck des employés. Chaque poste qui fait tourner
l'extension GNOME [ERPLibre Home](https://github.com/TechnoLibre/erplibre-home-gnome-extension)
s'inscrit auprès de cette base, puis y remonte son état et les événements de
ses decks : quels decks sont branchés, depuis quand, quel programme les
pilote et si leur service tourne. Odoo n'ouvre jamais de connexion vers un
poste.

L'inventaire appartient à son employé ; un gestionnaire voit tout le parc.
Personne ne l'écrit à la main : seules les routes des postes l'écrivent.

## Menus

| Menu | Qui | Contenu |
|---|---|---|
| Stream Deck › Mes postes | tout employé | ses postes ; le bouton *Ajouter un poste* affiche un code d'appairage |
| Stream Deck › Mes decks | tout employé | les decks que ses postes tiennent ou ont tenus |
| Stream Deck › Parc › Postes, Decks, Événements | gestionnaire | tout, en lecture, sauf le nom, l'archivage et le jeton d'un poste |

Un poste montre ce que disait sa dernière remontée : système
d'exploitation, versions de GNOME Shell, de l'extension et du contrat,
branche et commit du checkout ERPLibre, programme du deck et état de son
service, ses decks et ses événements. Son employé peut le renommer et
révoquer son jeton ; le gestionnaire peut aussi l'archiver.

## Inscrire un poste

Dans les préférences de l'extension, page *Inventaire Odoo*, ajouter cette
base par son URL et le nom de la base, puis choisir l'une des trois
méthodes :

- **Code d'appairage** : *Mes postes › Ajouter un poste* affiche un code de
  8 caractères, valable 10 minutes, une seule fois, pour l'employé qui l'a
  demandé.
- **Clé d'API** de l'employé (*Préférences › Sécurité du compte*).
- **Identifiant et mot de passe** de l'employé. Un compte dont l'accès RPC
  est limité aux clés d'API, comme avec l'authentification à deux
  facteurs, passe par l'une des deux autres méthodes.

La clé ou le mot de passe ne sert qu'à l'inscription et n'est gardé nulle
part. L'inscription rend un **jeton de poste**, que l'extension garde dans
le trousseau GNOME ; Odoo n'en garde que le SHA-256. Réinscrire le même
poste garde sa fiche et remplace son jeton. Des identifiants erronés
répétés depuis une même adresse sont soumis à la temporisation des
connexions d'Odoo.

## Accès

| Groupe | Postes | Decks | Événements |
|---|---|---|---|
| Utilisateur (tout utilisateur interne) | les siens : lire, renommer, révoquer le jeton | ceux que ses postes tiennent ou ont tenus, en lecture | ceux de ses postes, et tous ceux d'un deck qu'il peut lire |
| Gestionnaire | tous : lire, renommer, archiver, révoquer le jeton | tous, en lecture | tous, en lecture |

Un deck prêté à un autre employé suit le poste qui le tient. Le prêteur lit
toujours le deck et tout son historique, y compris les événements survenus
à l'autre poste : chaque événement porte une copie du nom de son poste et
de son employé, si bien que le prêteur n'a pas besoin de la fiche de
l'autre poste, et ne la reçoit pas.

Archiver un utilisateur archive ses postes et révoque leurs jetons ; les
postes, leurs decks et leurs événements restent lisibles du gestionnaire.
Les codes d'appairage ne sont lisibles de personne.

## Protocole de remontée 1.0

Le [CONTRACT.md](https://github.com/TechnoLibre/erplibre-home-gnome-extension/blob/main/CONTRACT.md)
de l'extension décrit le même protocole du côté du poste.

Le client envoie d'abord `GET <url>/web/login?db=<base>` avec un pot à
témoins pour choisir la base, puis chaque appel est un `POST` d'un objet
JSON, auquel répond un objet JSON, sous `/streamdeck/v1/`. Toute autre
méthode HTTP reçoit 405. Chaque corps porte `"protocol": "1.0"` : une
version majeure inconnue est refusée, une version mineure plus récente est
acceptée et ses clés inconnues ignorées. Chaque réponse porte `protocol` ;
une réponse d'erreur y ajoute `error`.

| Route | Authentification | Corps | Réponse 200 |
|---|---|---|---|
| `enroll` | les identifiants de la méthode | `method` (`pairing_code`, `api_key` ou `password`), `code`, `key` ou `login` + `password`, `fingerprint`, `hostname` | `workstation_id`, `token` |
| `report` | `Authorization: Bearer <jeton>` | `state`, `events`, `lost_events` | `accepted` (les uuid des événements), `heartbeat_s` (900) |
| `unenroll` | `Authorization: Bearer <jeton>` | rien d'autre | rien d'autre ; le jeton est révoqué |

- `fingerprint` : 64 chiffres hexadécimaux en minuscules, le HMAC-SHA256
  de l'identifiant de la machine avec pour clé l'utilisateur Linux, l'URL
  et la base ; l'identifiant brut ne quitte jamais le poste.
- `state` : nom d'hôte, système d'exploitation, versions de GNOME Shell, de
  l'extension et du contrat, branche et commit ERPLibre, programme du
  deck, état du service (`active`, `failed`, `inactive`, `absent`) et les
  decks branchés en ce moment (numéro de série, identifiant produit USB,
  chemin USB, firmware). Les decks du poste absents de la liste deviennent
  débranchés.
- `events` : `plugged`, `unplugged` ou `service_changed`, chacun avec son
  propre uuid et l'heure où il a été observé. Un uuid déjà enregistré est
  accusé de nouveau sans changement : une remontée renvoyée ne crée rien.
  Une heure de plus de 5 minutes en avance sur la réception est remplacée
  par l'heure de réception.
- `lost_events` : le total cumulé des événements que le poste a abandonnés
  sans les envoyer ; Odoo garde le plus grand total reçu.
- Un deck se reconnaît à son numéro de série, clé `sn:<numéro>` ; un deck
  sans numéro de série lisible se reconnaît à son poste, son identifiant
  produit et son chemin USB, clé `nosn:<poste>:<produit>:<chemin>`, et
  n'est jamais fusionné avec le deck d'un autre poste. Un numéro hors de
  `[A-Za-z0-9._-]{1,64}` est un 400 `bad_request` : sans `:`, il ne peut
  jamais nommer un deck sans numéro.
- Chaque texte d'un corps compte au plus 256 caractères et aucun
  caractère NUL, un identifiant produit USB a 4 chiffres hexadécimaux, et
  un deck, dans `state` comme dans un événement, porte un numéro de série
  ou un chemin USB ; tout autre cas est un 400 `bad_request` et rien
  n'est écrit.

| Statut | `error` | Sens |
|---|---|---|
| 400 | `bad_request` | le corps n'est pas du JSON, ou une valeur manque, est du mauvais type ou trop longue ; rien n'est écrit |
| 400 | `protocol_unsupported` | version majeure inconnue |
| 401 | `credentials_refused` | clé ou mot de passe erroné, code d'appairage inconnu, utilisé ou expiré, ou temporisation des connexions |
| 401 | `token_invalid` | jeton absent, inconnu ou révoqué |
| 403 | `user_inactive` | l'employé est archivé, ou n'est pas utilisateur Stream Deck (un compte portail, par exemple) |

Ni un corps, ni un en-tête, ni une réponse n'est journalisé, et chaque
réponse est marquée `Cache-Control: no-store`.

## Traductions

Le français canadien (`fr_CA`) couvre chaque terme du module : menus, vues,
champs et messages.