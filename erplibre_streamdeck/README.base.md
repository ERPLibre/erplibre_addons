<!---------------------------->
<!-- multilingual suffix: en, fr -->
<!-- no suffix: en -->
<!---------------------------->

<!-- [en] -->

# ERPLibre — Stream Deck

The inventory of the employees' Stream Decks. Each workstation that runs the
GNOME extension [ERPLibre Home](https://github.com/TechnoLibre/erplibre-home-gnome-extension)
enrolls with this database, then reports its state and its deck events
here: which decks are plugged in, since when, which program drives them and
whether their service runs. Odoo never opens a connection to a workstation.

The inventory belongs to its employee; a manager sees the whole fleet.
Nobody writes it by hand: only the workstation routes write it.

## Menus

| Menu | Who | Content |
|---|---|---|
| Stream Deck › My workstations | every employee | their workstations; the button *Add a workstation* shows a pairing code |
| Stream Deck › My decks | every employee | the decks their workstations hold or have held |
| Stream Deck › Fleet › Workstations, Decks, Events | manager | everything, read-only, except the name, the archive flag and the token of a workstation |

A workstation shows what its last report said: operating system, GNOME
Shell, extension and contract versions, branch and commit of the ERPLibre
checkout, deck program and the state of its service, its decks and its
events. Its employee may rename it and revoke its token; the manager may
also archive it.

## Enrolling a workstation

In the extension preferences, page *Odoo inventory*, add this database by
its URL and database name, then choose one of three methods:

- **Pairing code**: *My workstations › Add a workstation* shows a code of 8
  characters, valid 10 minutes, once, for the employee who asked for it.
- **API key** of the employee (*Preferences › Account Security*).
- **Login and password** of the employee. An account whose RPC access is
  limited to API keys, as with two-factor authentication, uses one of the
  two other methods.

The key or the password serves the enrollment only and is kept nowhere.
Enrollment returns a **workstation token**, which the extension keeps in
the GNOME keyring; Odoo keeps only its SHA-256. Enrolling the same
workstation again keeps its record and replaces its token. Repeated wrong
credentials from one address are put on Odoo's login cooldown.

## Access

| Group | Workstations | Decks | Events |
|---|---|---|---|
| User (every internal user) | their own: read, rename, revoke the token | those their workstations hold or have held, read-only | those of their workstations, and every event of a deck they can read |
| Manager | all: read, rename, archive, revoke the token | all, read-only | all, read-only |

A deck lent to another employee follows the workstation that holds it. The
lender still reads the deck and its whole history, the events at the other
workstation included: each event carries a copy of the name of its
workstation and of its employee, so the lender never needs, nor gets, the
other workstation's record.

When a workstation reports a deck that another workstation holds, the deck
moves to it without confirmation, and Odoo adds an event *Changed
workstation* (`moved`) dated at the reception. It names the new workstation
and its employee, and the workstation the deck left, each by a copy of its
name. This event alone proves that the former workstation had the deck: its
employee keeps reading the deck and its history, even when that
workstation never sent an event of it. The same workstation reporting the
deck again moves nothing.

Archiving a user archives their workstations and revokes their tokens; the
workstations, their decks and their events stay readable by the manager.
Pairing codes are readable by nobody.

## Wire protocol 1.0

The extension's
[CONTRACT.md](https://github.com/TechnoLibre/erplibre-home-gnome-extension/blob/main/CONTRACT.md)
describes the same protocol from the workstation side.

The client first sends `GET <url>/web/login?db=<db>` with a cookie jar to
select the database, then each call is a `POST` of a JSON object, answered
by a JSON object, under `/streamdeck/v1/`. Another HTTP method gets 405.
Every body carries `"protocol": "1.0"`: an unknown major version is refused,
a newer minor version is accepted and its unknown keys ignored. Every reply
carries `protocol`; an error reply adds `error`.

| Route | Authentication | Body | Reply 200 |
|---|---|---|---|
| `enroll` | the method's credentials | `method` (`pairing_code`, `api_key` or `password`), `code`, `key` or `login` + `password`, `fingerprint`, `hostname` | `workstation_id`, `token` |
| `report` | `Authorization: Bearer <token>` | `state`, `events`, `lost_events` | `accepted` (the uuids of the events), `heartbeat_s` (900) |
| `unenroll` | `Authorization: Bearer <token>` | nothing else | nothing else; the token is revoked |

- `fingerprint`: 64 lowercase hexadecimal digits, the HMAC-SHA256 of the
  machine identifier keyed by the Linux user, the URL and the database; the
  raw identifier never leaves the workstation.
- `state`: host name, operating system, GNOME Shell, extension and contract
  versions, ERPLibre branch and commit, deck program, service state
  (`active`, `failed`, `inactive`, `absent`) and the decks connected now
  (serial number, USB product id, USB path, firmware). The decks of the
  workstation missing from the list become disconnected.
- `events`: `plugged`, `unplugged` or `service_changed`, each with its own
  uuid and the time it was observed. `moved` is written by Odoo only: a
  report that carries it is a 400 `bad_request`. A uuid already stored is
  acknowledged again without change, so a report sent again creates
  nothing. A time more than 5 minutes ahead of the reception is replaced
  by the reception time.
- `lost_events`: the running total of events the workstation dropped
  unsent; Odoo keeps the largest total received.
- A deck is known by its serial number, key `sn:<serial>`; a deck without
  a readable serial number is known by its workstation, product id and
  USB path, key `nosn:<workstation>:<product>:<path>`, and is never
  merged with a deck of another workstation. A serial outside
  `[A-Za-z0-9._-]{1,64}` is a 400 `bad_request`: having no `:`, it can
  never name a deck without serial.
- Every text of a body holds at most 256 characters and no NUL
  character, a USB product id is 4 hexadecimal digits, and a deck, in
  `state` as in an event, carries a serial number or a USB path;
  anything else is a 400 `bad_request` and nothing is written.

| Status | `error` | Meaning |
|---|---|---|
| 400 | `bad_request` | the body is not JSON, or a value is missing, of the wrong type or too long; nothing is written |
| 400 | `protocol_unsupported` | unknown major version |
| 401 | `credentials_refused` | wrong key or password, unknown, used or expired pairing code, or login cooldown |
| 401 | `token_invalid` | missing, unknown or revoked token |
| 403 | `user_inactive` | the employee is archived, or is not a Stream Deck user (a portal account, for instance) |

Neither a body, a header nor a reply is logged, and every reply is marked
`Cache-Control: no-store`.

## Translations

Canadian French (`fr_CA`) covers every term of the module: menus, views,
fields and messages.

<!-- [fr] -->

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

Quand un poste remonte un deck que tient un autre poste, le deck passe à ce
poste sans confirmation, et Odoo ajoute un événement *Changé de poste*
(`moved`) daté de la réception. Il nomme le nouveau poste et son employé,
et le poste que le deck a quitté, chacun par une copie de son nom. Cet
événement suffit à prouver que l'ancien poste a eu le deck : son employé
lit toujours le deck et son historique, même si ce poste n'en a jamais
envoyé d'événement. Le même poste qui remonte de nouveau le deck ne
déplace rien.

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
  propre uuid et l'heure où il a été observé. `moved` n'est écrit que par
  Odoo : une remontée qui le porte est un 400 `bad_request`. Un uuid déjà
  enregistré est accusé de nouveau sans changement : une remontée renvoyée
  ne crée rien. Une heure de plus de 5 minutes en avance sur la réception
  est remplacée par l'heure de réception.
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
