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
| Stream Deck › Settings | administrator | the *Stream Deck* section of the Settings: the monitoring |

A workstation shows what its last report said: operating system, GNOME
Shell, extension and contract versions, branch and commit of the ERPLibre
checkout, deck program and the state of its service since when, its decks
and its events. Its employee may rename it and revoke its token; the
manager may also archive it. *Fleet › Workstations* adds the column
*Silent since* and the filter *Silent*.

A workstation and a deck each carry their thread, where the monitoring
posts its activities and notes. Every list of events names each event by
its label: the state of the service for a service change (*Service
started*, *failed*, *stopped*, *absent*), the kind for any other; the
history filters on each label.

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
| User (every internal user) | their own: read, rename, revoke the token | those their workstations hold or have held, read-only | those of their workstations, and those of a deck they hold or have held, from their first holding on |
| Manager | all: read, rename, archive, revoke the token | all, read-only | all, read-only |

A deck lent to another employee follows the workstation that holds it.
Each employee reads the history of a deck from the moment one of their
workstations first held it: when the deck was created on it, or when a
*Changed workstation* event moved it there. Odoo dates that moment itself,
never with a time the workstation sent, and keeps it when the deck comes
back after a loan. The lender therefore still reads the deck and its whole
history from their first holding on, the events at the other workstation
included: each event carries a copy of the name of its workstation and of
its employee, so the lender never needs, nor gets, the other workstation's
record. The borrower, or a workstation that reports the serial number of
another deck, reads nothing from before its arrival.

When a workstation reports a deck that another workstation holds, the deck
moves to it without confirmation, and Odoo adds an event *Changed
workstation* (`moved`) dated at the reception. It names the new workstation
and its employee, and the workstation the deck left, each by a copy of its
name. Its employee becomes a holder of the deck from that moment, unless
they held it before; the employee of the former workstation keeps
reading the deck and its history, even when that workstation never sent
an event of it. The same workstation reporting the deck again moves
nothing.

Archiving a user archives their workstations and revokes their tokens; the
workstations, their decks and their events stay readable by the manager.
Pairing codes are readable by nobody.

## Monitoring

Odoo watches four problems: a deck service that stays failed, a silent
workstation, a deck unplugged for long and a deck that changed
workstation. It always writes the history. It opens Odoo activities only
when *Settings › Stream Deck* enables them, which is off by default.

### History, always

| Event | Written by | When |
|---|---|---|
| *Service started*, *failed*, *stopped*, *absent* (`service_changed`) | the workstation | its deck service changes state |
| *Workstation silent* (`silent`) | Odoo | the workstation has sent no report for the silent delay; dated the end of that delay after its last report |
| *Workstation heard again* (`heard_again`) | Odoo | the first report after a silence; dated its reception |
| *Changed workstation* (`moved`) | Odoo | a workstation reports a deck that another one holds (see Access) |

A deck unplugged for long has no event of its own: its `unplugged` event
already dates it.

The cron *Stream Deck: watch workstations and decks* runs every 5
minutes, which is the granularity of every delay. It marks a workstation
silent once (*Silent since*); its next report clears the mark, and so do
archiving it and removing its token. A workstation that is archived, has
no token (unenrolled or revoked) or has never reported never goes
silent. The extension reports every 15 minutes and not while the screen
is locked: a workstation turned off for the night, asleep or locked
beyond the delay goes silent, then is heard again at its next report.

### Activities, on demand

| Problem | Activity type, on | Opens | Closes |
|---|---|---|---|
| Deck service failed | *Deck service failed*, on the workstation | the service has stayed `failed` for its delay | by itself, at the report that carries another state |
| Workstation silent | *Workstation silent*, on the workstation | the workstation goes silent | by itself, at its next report |
| Deck unplugged for long | *Deck unplugged for long*, on the deck | the deck has been unplugged for its delay, counted from its last sighting or its last `unplugged` event, whichever is later | by itself, at the report that shows it plugged in |
| Deck changed workstation | *Deck changed workstation*, on the deck | at the report that moves the deck | by a person; while one is open, whoever it is assigned to, a new move opens none and posts a note to the deck's thread |

- **Recipient.** *Employee*: the employee of the workstation, or of the
  workstation that holds the deck; for a move, the new holder, the lender
  reads the move in the history. *Manager*, the default: the user named
  in the Settings. *Employee and manager*: one activity for each.
- **Never a duplicate.** A record has at most one open activity of a type
  per assigned user. A deck with an open *Deck changed workstation*
  activity opens no other at a new move, even for another holder: the
  move is posted as a note to the deck's thread. A *Deck service
  failed* or *Deck unplugged for long* activity marked done while its
  problem lasts opens again at the next run of the cron; a silence opens
  its activity once.
- **Closing.** A closed activity stays done, with the feedback « Resolved
  at <time>: <what happened> », the time in the time zone of the assigned
  user (UTC without one) and the text in their language. Archiving a
  workstation or its employee, or revoking its token, closes its
  activities and the *Deck unplugged for long* activities of its decks
  with « the workstation is archived » or « the workstation is
  unenrolled ». Archiving a user, from the Settings or by their departure,
  closes the activities still assigned to them, *Deck changed workstation*
  included, with « the assigned user is archived », where Odoo would
  delete them. Closing does not depend on the Settings: an activity opened
  before they were disabled still closes.
- **Archived manager.** When the named manager is archived later, only
  the employee part opens, and each run of the cron writes a warning to
  the log, which names nobody.
- **Access.** An activity is read with its record. An employee reads the
  activities of their workstations, the manager's included, and those of
  the decks they hold or held, from their first holding on, plus those
  assigned to them; never those of another employee's workstation. The
  rest of a deck's thread, its messages and attached files, is read from
  the first holding on as well, the message that closes an activity
  counting from the opening of that activity. On a workstation's thread,
  the employee posts, edits their own messages and closes their own
  activities; only a manager edits, closes or deletes those of others.
  Only the monitoring creates activities of its four types.
- **Notification.** Odoo tells the assigned user of a new activity as it
  does for any activity (inbox or e-mail, by their preference). The module
  sends no e-mail and no notification of its own. Such an e-mail goes
  through Odoo's mail queue: neither a report nor the cron waits on the
  mail server.

### Settings › Stream Deck

Reserved to administrators, as the whole Settings page. Each setting is
the `ir.config_parameter` `erplibre_streamdeck.<key>`.

| Setting | Key | Default | Bound |
|---|---|---|---|
| Stream Deck detection activities | `activities_enabled` | off | — |
| Activities for | `activity_recipient` | Manager | Employee, Manager, Employee and manager |
| Activity manager | `activity_manager_id` | empty | required to enable the activities for Manager or Employee and manager; offered among the Stream Deck managers |
| Deck service failed, Workstation silent, Deck changed workstation, Deck unplugged for long | `alert_service_failed`, `alert_silent`, `alert_moved`, `alert_unplugged` | on | — |
| Silent after (minutes) | `silent_after_min` | 60 | 30 at least: one missed heartbeat is not silence |
| Unplugged for long after (hours) | `unplugged_after_h` | 72 | 1 at least |
| Service failed for (minutes) | `service_failed_after_min` | 10 | 0 at least |

The silent delay also dates the *Workstation silent* event, so it holds
with the activities disabled. The 72 hours cover a weekend without an
alert for a laptop taken home; the 10 minutes let the deck service restart
by itself after a brief failure.

### What stays history only

- Every problem while the activities are disabled, the default.
- A problem whose box is cleared.
- A deck service failed, or a deck unplugged, for less than its delay.
- Nothing leaves Odoo: no e-mail, push notification or message beyond
  Odoo activities. The delays are global, never per workstation or per
  employee, and the health of the deck itself (firmware, keys) is not
  watched.

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
  uuid and the time it was observed. `moved`, `silent` and `heard_again`
  are written by Odoo only: a report that carries one is a 400
  `bad_request`. A uuid already stored is
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
| Stream Deck › Paramètres | administrateur | la section *Stream Deck* des Paramètres : la surveillance |

Un poste montre ce que disait sa dernière remontée : système
d'exploitation, versions de GNOME Shell, de l'extension et du contrat,
branche et commit du checkout ERPLibre, programme du deck et état de son
service depuis quand, ses decks et ses événements. Son employé peut le
renommer et révoquer son jeton ; le gestionnaire peut aussi l'archiver.
*Parc › Postes* ajoute la colonne *Muet depuis* et le filtre *Muets*.

Un poste et un deck portent chacun leur fil, où la surveillance pose ses
activités et ses notes. Chaque liste d'événements nomme l'événement par
son libellé : l'état du service pour un changement de service (*Service
démarré*, *en échec*, *arrêté*, *absent*), la sorte pour tout autre ;
l'historique filtre sur chaque libellé.

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
| Utilisateur (tout utilisateur interne) | les siens : lire, renommer, révoquer le jeton | ceux que ses postes tiennent ou ont tenus, en lecture | ceux de ses postes, et ceux d'un deck qu'il détient ou a détenu, à partir de sa première détention |
| Gestionnaire | tous : lire, renommer, archiver, révoquer le jeton | tous, en lecture | tous, en lecture |

Un deck prêté à un autre employé suit le poste qui le tient. Chaque
employé lit l'historique d'un deck à partir du moment où un de ses postes
l'a détenu pour la première fois : la création du deck sur ce poste, ou
l'événement *Changé de poste* qui l'y a amené. Odoo date ce moment
lui-même, jamais avec une heure envoyée par le poste, et le garde quand le
deck revient après un prêt. Le prêteur lit donc toujours le deck et tout
son historique depuis sa première détention, y compris les événements
survenus à l'autre poste : chaque événement porte une copie du nom de son
poste et de son employé, si bien que le prêteur n'a pas besoin de la fiche
de l'autre poste, et ne la reçoit pas. L'emprunteur, ou un poste qui
déclare le numéro de série d'un autre deck, ne lit rien d'avant son
arrivée.

Quand un poste remonte un deck que tient un autre poste, le deck passe à ce
poste sans confirmation, et Odoo ajoute un événement *Changé de poste*
(`moved`) daté de la réception. Il nomme le nouveau poste et son employé,
et le poste que le deck a quitté, chacun par une copie de son nom. Son
employé devient détenteur du deck à ce moment, à moins de l'avoir détenu
avant ; l'employé de l'ancien poste lit toujours le deck et son
historique, même si ce poste n'en a jamais envoyé d'événement. Le même
poste qui remonte de nouveau le deck ne déplace rien.

Archiver un utilisateur archive ses postes et révoque leurs jetons ; les
postes, leurs decks et leurs événements restent lisibles du gestionnaire.
Les codes d'appairage ne sont lisibles de personne.

## Surveillance

Odoo surveille quatre problèmes : un service du deck qui reste en échec,
un poste muet, un deck débranché longtemps et un deck changé de poste. Il
écrit toujours l'historique. Il n'ouvre d'activités Odoo que si
*Paramètres › Stream Deck* les active, ce qui n'est pas le cas par défaut.

### L'historique, toujours

| Événement | Écrit par | Quand |
|---|---|---|
| *Service démarré*, *en échec*, *arrêté*, *absent* (`service_changed`) | le poste | son service du deck change d'état |
| *Poste muet* (`silent`) | Odoo | le poste n'a envoyé aucune remontée pendant le délai de silence ; daté de la fin de ce délai après sa dernière remontée |
| *Poste revenu* (`heard_again`) | Odoo | la première remontée après un silence ; daté de sa réception |
| *Changé de poste* (`moved`) | Odoo | un poste remonte un deck que tient un autre poste (voir Accès) |

Un deck débranché longtemps n'a pas d'événement à lui : son événement
`unplugged` le date déjà.

Le cron *Stream Deck : surveiller les postes et les decks* tourne toutes
les 5 minutes, ce qui donne la granularité de chaque délai. Il marque un
poste muet une seule fois (*Muet depuis*) ; sa remontée suivante efface la
marque, tout comme son archivage et le retrait de son jeton. Un poste
archivé, sans jeton (désinscrit ou révoqué) ou qui n'a jamais remonté ne
devient jamais muet. L'extension remonte toutes les 15 minutes, et pas
pendant que l'écran est verrouillé : un poste éteint la nuit, en veille ou
verrouillé au-delà du délai devient muet, puis revient à sa remontée
suivante.

### Les activités, sur demande

| Problème | Type d'activité, sur | S'ouvre | Se ferme |
|---|---|---|---|
| Service du deck en échec | *Service du deck en échec*, sur le poste | le service est resté `failed` pendant son délai | seule, à la remontée qui porte un autre état |
| Poste muet | *Poste muet*, sur le poste | le poste devient muet | seule, à sa remontée suivante |
| Deck débranché longtemps | *Deck débranché longtemps*, sur le deck | le deck est débranché depuis son délai, compté de sa dernière apparition ou de son dernier événement `unplugged`, le plus récent des deux | seule, à la remontée qui le montre branché |
| Deck changé de poste | *Deck changé de poste*, sur le deck | à la remontée qui déplace le deck | par une personne ; tant qu'une est ouverte, quel que soit son destinataire, un nouveau déplacement n'en ouvre aucune et ajoute une note au fil du deck |

- **Destinataire.** *Employé* : l'employé du poste, ou du poste qui tient
  le deck ; pour un déplacement, le nouveau détenteur, le prêteur
  l'apprend par l'historique. *Gestionnaire*, par défaut : l'utilisateur
  nommé dans les Paramètres. *Employé et gestionnaire* : une activité à
  chacun.
- **Jamais de doublon.** Un enregistrement a au plus une activité ouverte
  d'un type par destinataire. Un deck qui a une activité *Deck changé de
  poste* ouverte n'en ouvre aucune autre à un nouveau déplacement, même
  pour un autre détenteur : le déplacement s'ajoute en note au fil du
  deck. Une activité *Service du deck en échec* ou *Deck débranché
  longtemps* marquée faite pendant que son problème dure se rouvre au
  passage suivant du cron ; un silence n'ouvre son activité qu'une fois.
- **Fermeture.** Une activité fermée reste faite, avec le retour « Résolu
  à <heure> : <ce qui s'est passé> », l'heure dans le fuseau du
  destinataire (UTC à défaut) et le texte dans sa langue. Archiver un
  poste ou son employé, ou révoquer son jeton, ferme ses activités et les
  activités *Deck débranché longtemps* de ses decks avec « le poste est
  archivé » ou « le poste est désinscrit ». Archiver un utilisateur,
  depuis les Paramètres ou par son départ, ferme les activités qui lui
  restent, *Deck changé de poste* compris, avec « l'utilisateur assigné
  est archivé », là où Odoo les supprimerait. La fermeture ne dépend pas
  des Paramètres : une activité ouverte avant leur désactivation se ferme
  encore.
- **Gestionnaire archivé.** Si le gestionnaire nommé est archivé ensuite,
  seule la part de l'employé s'ouvre, et chaque passage du cron écrit au
  journal un avertissement qui ne nomme personne.
- **Accès.** Une activité se lit avec son enregistrement. Un employé lit
  les activités de ses postes, celles du gestionnaire comprises, et celles
  des decks qu'il détient ou a détenus, à partir de sa première détention,
  plus celles qui lui sont assignées ; jamais celles du poste d'un autre
  employé. Le reste du fil d'un deck, ses messages et ses fichiers joints,
  se lit lui aussi à partir de la première détention, le message qui ferme
  une activité comptant de l'ouverture de celle-ci. Au fil d'un poste,
  l'employé publie, modifie ses propres messages et ferme ses propres
  activités ; seul un gestionnaire modifie, ferme ou supprime ceux des
  autres. Seule la surveillance crée des activités de ses quatre types.
- **Notification.** Odoo prévient le destinataire d'une nouvelle activité
  comme pour toute activité (boîte de réception ou courriel, selon sa
  préférence). Le module n'envoie aucun courriel ni aucune notification
  de son côté. Ce courriel passe par la file des courriels d'Odoo : ni une
  remontée ni le cron n'attendent le serveur de courriel.

### Paramètres › Stream Deck

Réservés aux administrateurs, comme toute la page Paramètres. Chaque
paramètre est l'`ir.config_parameter` `erplibre_streamdeck.<clé>`.

| Paramètre | Clé | Défaut | Borne |
|---|---|---|---|
| Activités de détection Stream Deck | `activities_enabled` | désactivé | — |
| Activités pour | `activity_recipient` | Gestionnaire | Employé, Gestionnaire, Employé et gestionnaire |
| Gestionnaire des activités | `activity_manager_id` | vide | requis pour activer les activités pour Gestionnaire ou Employé et gestionnaire ; proposé parmi les gestionnaires Stream Deck |
| Service du deck en échec, Poste muet, Deck changé de poste, Deck débranché longtemps | `alert_service_failed`, `alert_silent`, `alert_moved`, `alert_unplugged` | cochés | — |
| Muet après (minutes) | `silent_after_min` | 60 | 30 au moins : un battement manqué n'est pas un silence |
| Débranché longtemps après (heures) | `unplugged_after_h` | 72 | 1 au moins |
| Service en échec depuis (minutes) | `service_failed_after_min` | 10 | 0 au moins |

Le délai de silence date aussi l'événement *Poste muet* : il vaut même
activités désactivées. Les 72 heures couvrent une fin de semaine sans
alerte pour un portable emporté ; les 10 minutes laissent le service du
deck repartir seul après un échec bref.

### Ce qui reste de l'historique seulement

- Tout problème tant que les activités sont désactivées, le défaut.
- Un problème dont la case est décochée.
- Un service du deck en échec, ou un deck débranché, moins longtemps que
  son délai.
- Rien ne sort d'Odoo : ni courriel, ni notification push, ni message
  hors des activités Odoo. Les délais sont globaux, jamais par poste ni
  par employé, et la santé du deck lui-même (firmware, touches) n'est pas
  surveillée.

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
  propre uuid et l'heure où il a été observé. `moved`, `silent` et
  `heard_again` ne sont écrits que par Odoo : une remontée qui en porte un
  est un 400 `bad_request`. Un uuid déjà
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
