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

Odoo also holds the deck settings it wants on each workstation: the deck
program, the plugins turned off, the session refresh, the games and the
layout of the home keys of each deck model. The workstation receives them
in the reply to its report, and its employee applies them with a click
(see Configuration).

The inventory belongs to its employee; a manager sees the whole fleet.
Nobody writes it by hand: only the workstation routes write it.

## Menus

| Menu | Who | Content |
|---|---|---|
| Stream Deck › My workstations | every employee | their workstations; the button *Add a workstation* shows a pairing code |
| Stream Deck › My decks | every employee | the decks their workstations hold or have held |
| Stream Deck › Fleet › Workstations, Decks, Events | manager | everything, read-only, except the name, the archive flag, the token and the configuration of a workstation |
| Stream Deck › Configuration › Profiles, Deck models, Key layouts, Catalog, First pilot | manager | the configuration layers: reusable profiles, and the settings of each deck model; every key layout and the catalog they choose from; the first-pilot policy |
| Stream Deck › Settings | administrator | the *Stream Deck* section of the Settings: the monitoring and the first pilot |

A workstation shows what its last report said: operating system, GNOME
Shell, extension and contract versions, branch and commit of the ERPLibre
checkout, deck program and the state of its service since when, its decks
and its events. Its employee may rename it and revoke its token; the
manager may also archive it. *Fleet › Workstations* adds the column
*Silent since* and the filter *Silent*. The filters *Configuration
pending* and *Configuration refused* select the workstations by the state
of their configuration, and the tab *Configuration* of a workstation shows
its profile, its effective settings with the layer and the lock of each,
its overrides, the key layout of each connected deck, its own key
layouts and the state of the revision offered to it.

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
| User (every internal user) | their own: read, rename, revoke the token, pick a selectable profile, override the free settings | those their workstations hold or have held, read-only | those of their workstations, and those of a deck they hold or have held, from their first holding on |
| Manager | all: read, rename, archive, revoke the token, assign any profile, override and lock settings | all, read-only | all, read-only |

A deck lent to another employee follows the workstation that holds it.
Each employee reads the history of a deck from the moment one of their
workstations first held it: when the deck was created on it, or when a
*Changed workstation* event moved it there. Odoo dates that moment itself,
never with a time the workstation sent, and keeps it when the deck comes
back after a loan. The lender therefore still reads the deck and its whole
history from their first holding on, the events at the other workstation
included: each event carries a copy of the name of its workstation and of
its employee, so the lender never needs, nor gets, the other workstation's
record. The borrower reads nothing from before its arrival. A workstation
that only sends an event carrying the serial number of a deck held
elsewhere reads that event and the deck's name on it, never the deck's
record nor its history.

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

The configuration layers. A manager creates and changes the profiles, the
deck models and every settings line, and alone sets a lock. An employee
reads the selectable profiles, the profile of each of their workstations
and every deck-model layer, which hold nothing personal; never a profile
assigned only to another employee's workstation, nor the overrides of
another employee. On their own workstations they create, change and
delete the overrides of the settings that no layer locks, never *Locked*
nor *Source*. They pick a selectable profile, in place of no profile or of
another selectable one only: a profile the manager assigned without
making it selectable stays, and an employee never clears a profile. The
state of the configuration (revisions, offered and applied values, state,
reason, first-pilot choice) is written by the report route only.

The key layouts follow the same rules, the lock being on a whole layout:
an employee reads the layouts of the layers they read, and on their own
workstations creates, changes and deletes the layouts, and their keys, of
the deck models that no layer locks, never *Locked*, *Source* nor *Kept
in the workstation's file*. Everyone reads the catalog; only the report
route adds to it.

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
| First pilot | `first_pilot_policy` | Ask the employee | Keep local values, Take Odoo's values; see Configuration |

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

## Configuration

Odoo manages a closed list of four settings, each one line of the
workstation's `~/.config/erplibre-home/streamdeck.conf`:

| Setting | Key on the wire | Line of the file | Values | Restarts the deck service |
|---|---|---|---|---|
| Deck program | `deck_program` | `DECK_PROGRAM` | `tiler`, `controller`, `none` | yes |
| Plugins turned off | `plugins_off` | `DECK_PLUGINS_OFF` | at most 64 plugin ids `[a-z][a-z0-9_]{0,63}`, joined by commas | yes |
| Session refresh (seconds) | `session_refresh_sec` | `DECK_SESSION_REFRESH_SEC` | a number from 0.5 to 60 | yes |
| Games | `games` | `GAMES` | `on`, `off` | no |

No path, no command and no plugin to turn on: Odoo cannot make a
workstation run anything. A value is typed bare in a line (a word, plugin
ids separated by commas, a number) and stored as JSON; a value outside
this list is refused at the write. The tab *Configuration* lists the
plugins the workstation found on its disk.

### Layers and locks

A setting takes its value from the last of three layers that sets it:

1. the **profile** of the workstation (*Configuration › Profiles*); an
   archived profile counts for nothing;
2. the **deck model**: the settings of the model of each connected deck
   (*Configuration › Deck models*, by USB product id). With decks of
   several models, their layers apply by ascending product id, the
   highest winning, and the workstation form warns about it;
3. the **workstation** itself: its overrides, in its tab *Configuration*.

A line marked *Locked* stops its setting there: a locked profile line
ignores the models and the workstation, a locked model line ignores the
next models and the workstation. Only a manager sets a lock. A setting
that no layer sets stays the employee's, on the workstation, and Odoo
never adopts it.

A profile marked *Selectable* is offered to the employees, who each pick
one for their own workstations. The manager assigns any profile to any
workstation.

### Offer and application

At each report of the pilot, Odoo computes the effective configuration
of the workstation. When its SHA-256 differs from the last one offered,
the *Offered revision* grows by one. The reply carries the revision and
the extension announces it; nothing changes on the workstation until its
employee clicks *Apply*. The extension then rewrites the managed lines of
`streamdeck.conf`, keeps every other line, and restarts the deck service
when a setting that needs it changed and the service is running; a
stopped deck service is never started. Its next report says whether the
revision was applied or refused, and why.

| Configuration | Meaning |
|---|---|
| Unmanaged | no layer sets a setting of the workstation, it never reported with protocol 1.1, or its extension does not check this database as the pilot; a revision pending until then is withdrawn |
| Pending | a revision is offered and not applied yet, since *Configuration pending since* |
| Applied | the workstation applied the offered revision |
| Refused | the workstation refused it; *Refusal reason* says why: `invalid:<key>` (`invalid:key_layouts` for the key layouts), `write_failed`, `restart_failed` or `unit_missing` |
| Changed locally | a setting changed in the file; Odoo offers it again |

An extension older than contract 1.3 reports without being piloted, and
the form says that it is too old. An extension of contract 1.3 is piloted
without the key layouts, which start with contract 1.4 (protocol 1.2).

### First pilot

The first time a workstation is piloted, its free settings may hold local
values that differ from Odoo's. The Stream Deck manager decides in
*Stream Deck › Configuration › First pilot*, as a Settings administrator
does in *Settings › Stream Deck*:

- **Ask the employee**, the default: the extension asks once whether to
  keep the local values, which then become overrides of the workstation
  with the source *Workstation file*, or to take Odoo's. The form says
  that Odoo waits for this choice and names the settings concerned.
- **Keep local values**: Odoo adopts them at once, without asking.
- **Take Odoo's values**: nothing is adopted.

A local value that is empty, or already Odoo's, raises no question.
Locked settings are always offered for the usual confirmation, whatever
the choice. The workstation keeps the answer in *First pilot choice*;
applying a first revision counts as *Take Odoo's values*.

### Local changes

After a revision is applied, a managed setting changed in the file, from
the menu TODO › Stream Deck for instance, is handled at the next report:

- a **free** setting becomes an override of the workstation, with the
  source *Workstation file*, and raises no question: the next revision
  equals the file, and the extension records it applied silently;
- a **locked** setting, or a setting removed from the file or made
  invalid there, is offered again under a new revision, which the
  employee confirms as any other.

### Key layouts

The home screen of each deck model is laid out in Odoo. A key layout is
for one USB product id and belongs to a profile, a deck model or a
workstation: the tab *Key layouts* of each, or *Configuration › Key
layouts*. Its form lists one line per key: the index (0 the top left
key, numbered row by row), the action and the icon chosen in the
catalog, and a label of at most 16 characters without control character.
*Create the keys* adds an empty line for each key of the model, and the
preview shows the grid. An action is the home key of a plugin
(`plugin:<id>`), a key of the dashboard (`tiles`) or a black key
(`empty`); a key without action is left to the deck program, which
places its fixtures and its dashboard there. A plugin can have one home
key per layout, and a plugin that the layout does not name gets none: the
form warns of the *Plugins without a key*.

The layouts of a model fold as the settings do, profile < deck model <
workstation, and *Locked* holds the whole layout: a locked layout stops
the fold for its model. The home key of a plugin turned off, by Odoo or
else by the workstation's file, goes as a black key: the workstation
refuses a layout naming a plugin turned off. Only the layouts of the connected decks go to
the workstation, in the setting `key_layouts` of the revision, which is
locked when one of them is; the extension writes them to
`~/.config/erplibre-home/keymap.json` when the employee applies the
revision. A model that no layer lays out keeps the automatic layout of
the deck program.

The catalog (*Configuration › Catalog*) is the union of what the
workstations report: the actions, the icons and the geometry of each
deck model. An item that no workstation reports any more stays, with the
date it was last seen, to the hour. A model that no workstation reported takes its
geometry from a table shipped with the module.

A layout changed in the file after its revision was applied is handled
as a setting, by the SHA-256 of each model's layout (canonical JSON: keys
sorted, no space, every character outside ASCII escaped as `\uXXXX`):

- a **free** layout becomes a layout of the workstation marked *Kept in
  the workstation's file*, with the source *Workstation file*, and Odoo
  sends no layout for that model any more; creating or changing one of
  its keys sends it again;
- a **locked** layout, or one removed from the file, is offered again.

The first-pilot question leaves the layouts out: only the extension
writes `keymap.json`.

### History of the configuration

| Event | When |
|---|---|
| *Configuration applied* (`config_applied`) | the workstation reports the offered revision applied; with its revision |
| *Configuration refused* (`config_refused`) | the workstation reports it refused; with its revision and reason |
| *Local setting adopted* (`config_adopted`) | a free local value becomes an override; with its settings, `key_layouts:<product id>` for a layout kept in the file |
| *Setting changed locally* (`config_drift`) | a locked setting, or a removed one, is offered again; with its settings, `key_layouts:<product id>` for a layout |

Odoo alone writes them, and they open no activity: the state is read on
the workstation. The history filters on each of them.

## Wire protocol 1.2

The extension's
[CONTRACT.md](https://github.com/TechnoLibre/erplibre-home-gnome-extension/blob/main/CONTRACT.md)
describes the same protocol from the workstation side.

The client first sends `GET <url>/web/login?db=<db>` with a cookie jar to
select the database, then each call is a `POST` of a JSON object, answered
by a JSON object, under `/streamdeck/v1/`. Another HTTP method gets 405.
Every body carries `"protocol"`: `"1.2"` for a workstation that takes in
the key layouts, `"1.1"` for one that takes in the settings only, `"1.0"`
before: an unknown major version is refused, a newer minor version is
accepted and its unknown keys ignored. Every reply carries `"protocol":
"1.2"`; an error reply adds `error`.

| Route | Authentication | Body | Reply 200 |
|---|---|---|---|
| `enroll` | the method's credentials | `method` (`pairing_code`, `api_key` or `password`), `code`, `key` or `login` + `password`, `fingerprint`, `hostname` | `workstation_id`, `token` |
| `report` | `Authorization: Bearer <token>` | `state`, `events`, `lost_events`, `config` (1.1) | `accepted` (the uuids of the events), `heartbeat_s` (900), `config` (1.1, to the pilot of a configured workstation) |
| `unenroll` | `Authorization: Bearer <token>` | nothing else | nothing else; the token is revoked |

- `fingerprint`: 64 lowercase hexadecimal digits, the HMAC-SHA256 of the
  machine identifier keyed by the Linux user, the URL and the database; the
  raw identifier never leaves the workstation.
- `state`: host name, operating system, GNOME Shell, extension and contract
  versions, ERPLibre branch and commit, deck program, service state
  (`active`, `failed`, `inactive`, `absent`) and the decks connected now
  (serial number, USB product id, USB path, firmware). The decks of the
  workstation missing from the list become disconnected. In 1.1,
  `deck_plugins` lists at most 128 ids of the deck plugins found on the
  workstation's disk; its repeats are dropped. In 1.2, `deck_catalog` is
  the catalog of the deck program, `{"format": 1, "actions", "icons",
  "models": {<product id>: {"cols", "rows", "keys"}}}`, added to the
  catalog of Odoo; larger than 32 KiB, or of another format, it is
  ignored, and an action or an icon of an unknown form is skipped, as is a
  model whose geometry fits no key (no key, or more keys than cells). The
  numbers of a geometry are integers from 0 to 256; anything else is a
  400 `bad_request`.
- `events`: `plugged`, `unplugged` or `service_changed`, each with its own
  uuid and the time it was observed. `moved`, `silent`, `heard_again`
  and the four `config_*` kinds are written by Odoo only: a report that
  carries one is a 400 `bad_request`. A uuid already stored is
  acknowledged again without change, so a report sent again creates
  nothing. A time more than 5 minutes ahead of the reception is replaced
  by the reception time.
- `lost_events`: the running total of events the workstation dropped
  unsent; Odoo keeps the largest total received.
- `config` (1.1, ignored in a 1.0 body): `{"pilot": false}` from a
  destination that is not the pilot of the workstation, which gets no
  `config` back. From the pilot, `{"pilot": true, "revision_applied",
  "current", "result", "choice"}`: `current` the four settings as the file
  holds them, null when absent or invalid; `result` the outcome of the
  last revision, `{"revision", "status", "reason", "at"}` with `status`
  `applied` or `refused`; `choice` the answer to the first-pilot question,
  `keep_local` or `take_odoo`, sent once. A value outside the schema, or
  an unknown status, reason or choice, is a 400 `bad_request`; a key
  outside the four settings is ignored. In 1.2, `current.key_layouts`
  maps the product id of each layout of `keymap.json` to the SHA-256 of
  that layout, null when the file holds none (at most 128), and the
  reason `invalid:key_layouts` is known.
- `config` of the reply: `{"revision", "hash", "settings", "locked"}`,
  plus `ask` during a first pilot under *Ask the employee*. `hash` is the
  SHA-256 of the canonical JSON of `settings` (keys sorted, no space),
  `locked` the locked settings, `ask` the free settings whose local value
  differs from Odoo's. In 1.2, `settings.key_layouts` maps the product
  id of each connected deck that Odoo lays out to `{"keys": [{"key",
  "action", "icon", "label"}]}`, by ascending key, `icon` and `label`
  only when set, at most 16 models; `locked` then lists `key_layouts`
  when one of these layouts is locked.
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

Odoo porte aussi les réglages du deck qu'il veut sur chaque poste : le
programme du deck, les plugins coupés, le rafraîchissement de session,
les jeux et la disposition des touches d'accueil de chaque modèle de
deck. Le poste les reçoit dans la réponse à sa remontée, et son employé
les applique d'un clic (voir Configuration).

L'inventaire appartient à son employé ; un gestionnaire voit tout le parc.
Personne ne l'écrit à la main : seules les routes des postes l'écrivent.

## Menus

| Menu | Qui | Contenu |
|---|---|---|
| Stream Deck › Mes postes | tout employé | ses postes ; le bouton *Ajouter un poste* affiche un code d'appairage |
| Stream Deck › Mes decks | tout employé | les decks que ses postes tiennent ou ont tenus |
| Stream Deck › Parc › Postes, Decks, Événements | gestionnaire | tout, en lecture, sauf le nom, l'archivage, le jeton et la configuration d'un poste |
| Stream Deck › Configuration › Profils, Modèles de deck, Dispositions des touches, Catalogue, Premier pilotage | gestionnaire | les couches de configuration : les profils réutilisables, et les réglages de chaque modèle de deck ; toutes les dispositions des touches et le catalogue où elles choisissent ; la politique du premier pilotage |
| Stream Deck › Paramètres | administrateur | la section *Stream Deck* des Paramètres : la surveillance et le premier pilotage |

Un poste montre ce que disait sa dernière remontée : système
d'exploitation, versions de GNOME Shell, de l'extension et du contrat,
branche et commit du checkout ERPLibre, programme du deck et état de son
service depuis quand, ses decks et ses événements. Son employé peut le
renommer et révoquer son jeton ; le gestionnaire peut aussi l'archiver.
*Parc › Postes* ajoute la colonne *Muet depuis* et le filtre *Muets*. Les
filtres *Configuration en attente* et *Configuration refusée* choisissent
les postes par l'état de leur configuration, et l'onglet *Configuration*
d'un poste montre son profil, ses réglages effectifs avec la couche et le
verrou de chacun, ses surcharges, la disposition des touches de chaque
deck branché, ses propres dispositions et l'état de la révision qui lui
est proposée.

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
| Utilisateur (tout utilisateur interne) | les siens : lire, renommer, révoquer le jeton, choisir un profil « au choix », surcharger les réglages libres | ceux que ses postes tiennent ou ont tenus, en lecture | ceux de ses postes, et ceux d'un deck qu'il détient ou a détenu, à partir de sa première détention |
| Gestionnaire | tous : lire, renommer, archiver, révoquer le jeton, assigner n'importe quel profil, surcharger et verrouiller les réglages | tous, en lecture | tous, en lecture |

Un deck prêté à un autre employé suit le poste qui le tient. Chaque
employé lit l'historique d'un deck à partir du moment où un de ses postes
l'a détenu pour la première fois : la création du deck sur ce poste, ou
l'événement *Changé de poste* qui l'y a amené. Odoo date ce moment
lui-même, jamais avec une heure envoyée par le poste, et le garde quand le
deck revient après un prêt. Le prêteur lit donc toujours le deck et tout
son historique depuis sa première détention, y compris les événements
survenus à l'autre poste : chaque événement porte une copie du nom de son
poste et de son employé, si bien que le prêteur n'a pas besoin de la fiche
de l'autre poste, et ne la reçoit pas. L'emprunteur ne lit rien d'avant
son arrivée. Un poste qui envoie seulement un événement portant le numéro
de série d'un deck tenu ailleurs lit cet événement et le nom du deck qu'il
porte, jamais la fiche du deck ni son historique.

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

Les couches de configuration. Un gestionnaire crée et modifie les
profils, les modèles de deck et toute ligne de réglage, et lui seul pose
un verrou. Un employé lit les profils « au choix », le profil de chacun
de ses postes et toutes les couches modèle, qui ne portent rien de
personnel ; jamais un profil assigné seulement au poste d'un autre
employé, ni les surcharges d'un autre employé. Sur ses propres postes, il
crée, modifie et supprime les surcharges des réglages qu'aucune couche ne
verrouille, jamais *Verrouillé* ni *Source*. Il choisit un profil « au
choix », seulement à la place d'aucun profil ou d'un autre profil « au
choix » : un profil que le gestionnaire a assigné sans le rendre « au
choix » reste, et un employé ne retire jamais un profil. L'état de la
configuration (révisions, valeurs proposées et appliquées, état, raison,
choix du premier pilotage) n'est écrit que par la route de remontée.

Les dispositions des touches suivent les mêmes règles, le verrou portant
sur une disposition entière : un employé lit les dispositions des couches
qu'il lit, et sur ses propres postes crée, modifie et supprime les
dispositions, et leurs touches, des modèles de deck qu'aucune couche ne
verrouille, jamais *Verrouillé*, *Source* ni *Gardée dans le fichier du
poste*. Tout le monde lit le catalogue ; seule la route de remontée y
ajoute.

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
| Premier pilotage | `first_pilot_policy` | Demander à l'employé | Garder les valeurs locales, Prendre les valeurs d'Odoo ; voir Configuration |

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

## Configuration

Odoo gère une liste fermée de quatre réglages, chacun une ligne du
fichier `~/.config/erplibre-home/streamdeck.conf` du poste :

| Réglage | Clé du fil | Ligne du fichier | Valeurs | Redémarre le service du deck |
|---|---|---|---|---|
| Programme du deck | `deck_program` | `DECK_PROGRAM` | `tiler`, `controller`, `none` | oui |
| Plugins coupés | `plugins_off` | `DECK_PLUGINS_OFF` | au plus 64 identifiants de plugins `[a-z][a-z0-9_]{0,63}`, joints par des virgules | oui |
| Rafraîchissement de session (secondes) | `session_refresh_sec` | `DECK_SESSION_REFRESH_SEC` | un nombre de 0.5 à 60 | oui |
| Jeux | `games` | `GAMES` | `on`, `off` | non |

Aucun chemin, aucune commande et aucun plugin à activer : Odoo ne peut
rien faire exécuter sur un poste. Une valeur se tape nue dans une ligne
(un mot, des identifiants de plugins séparés par des virgules, un nombre)
et se range en JSON ; une valeur hors de cette liste est refusée à
l'écriture. L'onglet *Configuration* liste les plugins que le poste a
trouvés sur son disque.

### Couches et verrous

Un réglage prend sa valeur de la dernière des trois couches qui le fixe :

1. le **profil** du poste (*Configuration › Profils*) ; un profil archivé
   ne compte pour rien ;
2. le **modèle de deck** : les réglages du modèle de chaque deck branché
   (*Configuration › Modèles de deck*, par identifiant produit USB). Avec
   des decks de plusieurs modèles, leurs couches s'appliquent par
   identifiant produit croissant, le plus grand l'emportant, et la fiche
   du poste en avertit ;
3. le **poste** lui-même : ses surcharges, dans son onglet
   *Configuration*.

Une ligne cochée *Verrouillé* arrête là son réglage : une ligne de profil
verrouillée ignore les modèles et le poste, une ligne de modèle
verrouillée ignore les modèles suivants et le poste. Seul un gestionnaire
pose un verrou. Un réglage qu'aucune couche ne fixe reste à l'employé,
sur le poste, et Odoo ne l'adopte jamais.

Un profil coché *Au choix* est proposé aux employés, qui en choisissent
chacun un pour leurs propres postes. Le gestionnaire assigne n'importe
quel profil à n'importe quel poste.

### Proposition et application

À chaque remontée du pilote, Odoo calcule la configuration effective du
poste. Quand son SHA-256 diffère de la dernière proposée, la *Révision
proposée* augmente de un. La réponse porte la révision et l'extension
l'annonce ; rien ne change sur le poste tant que son employé n'a pas
cliqué *Appliquer*. L'extension réécrit alors les lignes gérées de
`streamdeck.conf`, garde toute autre ligne, et redémarre le service du
deck quand un réglage qui l'exige a changé et que le service tourne ; un
service du deck arrêté n'est jamais démarré. Sa remontée suivante dit si
la révision a été appliquée ou refusée, et pourquoi.

| Configuration | Sens |
|---|---|
| Non gérée | aucune couche ne fixe de réglage du poste, il n'a jamais remonté en protocole 1.1, ou son extension ne coche pas cette base comme pilote ; une révision jusque-là en attente est retirée |
| En attente | une révision est proposée et pas encore appliquée, depuis *Configuration en attente depuis* |
| Appliquée | le poste a appliqué la révision proposée |
| Refusée | le poste l'a refusée ; *Raison du refus* dit pourquoi : `invalid:<clé>` (`invalid:key_layouts` pour les dispositions des touches), `write_failed`, `restart_failed` ou `unit_missing` |
| Changée localement | un réglage a changé dans le fichier ; Odoo le propose de nouveau |

Une extension plus ancienne que le contrat 1.3 remonte sans être pilotée,
et la fiche dit qu'elle est trop ancienne. Une extension du contrat 1.3
est pilotée sans les dispositions des touches, qui commencent au contrat
1.4 (protocole 1.2).

### Premier pilotage

La première fois qu'un poste est piloté, ses réglages libres peuvent
porter des valeurs locales qui diffèrent de celles d'Odoo. Le
gestionnaire du Stream Deck en décide dans *Stream Deck › Configuration ›
Premier pilotage*, comme l'administrateur des Paramètres dans
*Paramètres › Stream Deck* :

- **Demander à l'employé**, le défaut : l'extension demande une seule fois
  s'il garde les valeurs locales, qui deviennent alors des surcharges du
  poste de source *Fichier du poste*, ou s'il prend celles d'Odoo. La
  fiche dit qu'Odoo attend ce choix et nomme les réglages concernés.
- **Garder les valeurs locales** : Odoo les adopte aussitôt, sans
  demander.
- **Prendre les valeurs d'Odoo** : rien n'est adopté.

Une valeur locale vide, ou déjà celle d'Odoo, ne pose aucune question.
Les réglages verrouillés sont toujours proposés à la confirmation
habituelle, quel que soit le choix. Le poste garde la réponse dans *Choix
du premier pilotage* ; appliquer une première révision vaut *Prendre les
valeurs d'Odoo*.

### Changements locaux

Après l'application d'une révision, un réglage géré changé dans le
fichier, depuis le menu TODO › Stream Deck par exemple, se traite à la
remontée suivante :

- un réglage **libre** devient une surcharge du poste, de source *Fichier
  du poste*, sans question : la révision suivante égale le fichier, et
  l'extension la note appliquée sans rien annoncer ;
- un réglage **verrouillé**, ou un réglage retiré du fichier ou rendu
  invalide, est proposé de nouveau sous une nouvelle révision, que
  l'employé confirme comme toute autre.

### Dispositions des touches

L'écran d'accueil de chaque modèle de deck se dispose dans Odoo. Une
disposition des touches vaut pour un identifiant produit USB et
appartient à un profil, à un modèle de deck ou à un poste : l'onglet
*Dispositions des touches* de chacun, ou *Configuration › Dispositions
des touches*. Sa fiche liste une ligne par touche : l'index (0 la touche
en haut à gauche, numérotées rangée par rangée), l'action et l'icône
choisies dans le catalogue, et un libellé d'au plus 16 caractères sans
caractère de contrôle. *Créer les touches* ajoute une ligne vide pour
chaque touche du modèle, et l'aperçu montre la grille. Une action est la
touche d'accueil d'un plugin (`plugin:<id>`), une touche du tableau de
bord (`tiles`) ou une touche noire (`empty`) ; une touche sans action est
laissée au programme du deck, qui y place ses fixtures et son tableau de
bord. Un plugin a au plus une touche d'accueil par disposition, et un
plugin que la disposition ne nomme pas n'en a aucune : la fiche avertit
des *Plugins sans touche*.

Les dispositions d'un modèle se replient comme les réglages, profil <
modèle de deck < poste, et *Verrouillé* tient la disposition entière :
une disposition verrouillée arrête le repli pour son modèle. La touche
d'accueil d'un plugin coupé, par Odoo ou sinon par le fichier du poste,
part comme une touche noire : le poste refuse une disposition qui nomme
un plugin coupé. Seules les
dispositions des decks branchés vont au poste, dans le réglage
`key_layouts` de la révision, verrouillé quand l'une d'elles l'est ;
l'extension les écrit dans `~/.config/erplibre-home/keymap.json` quand
l'employé applique la révision. Un modèle qu'aucune couche ne dispose
garde la disposition automatique du programme du deck.

Le catalogue (*Configuration › Catalogue*) est l'union de ce que
remontent les postes : les actions, les icônes et la géométrie de chaque
modèle de deck. Un élément qu'aucun poste ne remonte plus reste, avec la
date où il a été vu la dernière fois, à l'heure près. Un modèle qu'aucun poste n'a
remonté prend sa géométrie dans une table livrée avec le module.

Une disposition changée dans le fichier après l'application de sa
révision se traite comme un réglage, par le SHA-256 de la disposition de
chaque modèle (JSON canonique : clés triées, sans espace, tout caractère
hors ASCII échappé en `\uXXXX`) :

- une disposition **libre** devient une disposition du poste marquée
  *Gardée dans le fichier du poste*, de source *Fichier du poste*, et
  Odoo n'envoie plus de disposition pour ce modèle ; créer ou changer une
  de ses touches la renvoie ;
- une disposition **verrouillée**, ou retirée du fichier, est proposée de
  nouveau.

La question du premier pilotage laisse les dispositions de côté : seule
l'extension écrit `keymap.json`.

### Historique de la configuration

| Événement | Quand |
|---|---|
| *Configuration appliquée* (`config_applied`) | le poste remonte la révision proposée appliquée ; avec sa révision |
| *Configuration refusée* (`config_refused`) | le poste la remonte refusée ; avec sa révision et sa raison |
| *Réglage local adopté* (`config_adopted`) | une valeur locale libre devient une surcharge ; avec ses réglages, `key_layouts:<identifiant produit>` pour une disposition gardée dans le fichier |
| *Réglage changé localement* (`config_drift`) | un réglage verrouillé, ou retiré, est proposé de nouveau ; avec ses réglages, `key_layouts:<identifiant produit>` pour une disposition |

Odoo seul les écrit, et ils n'ouvrent aucune activité : l'état se lit
sur le poste. L'historique filtre sur chacun d'eux.

## Protocole de remontée 1.2

Le [CONTRACT.md](https://github.com/TechnoLibre/erplibre-home-gnome-extension/blob/main/CONTRACT.md)
de l'extension décrit le même protocole du côté du poste.

Le client envoie d'abord `GET <url>/web/login?db=<base>` avec un pot à
témoins pour choisir la base, puis chaque appel est un `POST` d'un objet
JSON, auquel répond un objet JSON, sous `/streamdeck/v1/`. Toute autre
méthode HTTP reçoit 405. Chaque corps porte `"protocol"` : `"1.2"` pour
un poste qui reçoit les dispositions des touches, `"1.1"` pour un poste
qui ne reçoit que les réglages, `"1.0"` avant : une version majeure
inconnue est refusée, une version mineure plus récente est acceptée et ses
clés inconnues ignorées. Chaque réponse porte `"protocol": "1.2"` ; une
réponse d'erreur y ajoute `error`.

| Route | Authentification | Corps | Réponse 200 |
|---|---|---|---|
| `enroll` | les identifiants de la méthode | `method` (`pairing_code`, `api_key` ou `password`), `code`, `key` ou `login` + `password`, `fingerprint`, `hostname` | `workstation_id`, `token` |
| `report` | `Authorization: Bearer <jeton>` | `state`, `events`, `lost_events`, `config` (1.1) | `accepted` (les uuid des événements), `heartbeat_s` (900), `config` (1.1, au pilote d'un poste configuré) |
| `unenroll` | `Authorization: Bearer <jeton>` | rien d'autre | rien d'autre ; le jeton est révoqué |

- `fingerprint` : 64 chiffres hexadécimaux en minuscules, le HMAC-SHA256
  de l'identifiant de la machine avec pour clé l'utilisateur Linux, l'URL
  et la base ; l'identifiant brut ne quitte jamais le poste.
- `state` : nom d'hôte, système d'exploitation, versions de GNOME Shell, de
  l'extension et du contrat, branche et commit ERPLibre, programme du
  deck, état du service (`active`, `failed`, `inactive`, `absent`) et les
  decks branchés en ce moment (numéro de série, identifiant produit USB,
  chemin USB, firmware). Les decks du poste absents de la liste deviennent
  débranchés. En 1.1, `deck_plugins` liste au plus 128 identifiants des
  plugins du deck trouvés sur le disque du poste ; ses répétitions sont
  écartées. En 1.2, `deck_catalog` est le catalogue du programme du
  deck, `{"format": 1, "actions", "icons", "models": {<identifiant
  produit>: {"cols", "rows", "keys"}}}`, ajouté au catalogue d'Odoo ;
  plus grand que 32 Kio, ou d'un autre format, il est ignoré, et une
  action ou une icône d'une forme inconnue est sautée, comme un modèle
  dont la géométrie n'accueille aucune touche (aucune touche, ou plus de
  touches que de cases). Les nombres d'une géométrie sont des entiers de
  0 à 256 ; tout autre cas est un 400 `bad_request`.
- `events` : `plugged`, `unplugged` ou `service_changed`, chacun avec son
  propre uuid et l'heure où il a été observé. `moved`, `silent`,
  `heard_again` et les quatre sortes `config_*` ne sont écrits que par
  Odoo : une remontée qui en porte un est un 400 `bad_request`. Un uuid déjà
  enregistré est accusé de nouveau sans changement : une remontée renvoyée
  ne crée rien. Une heure de plus de 5 minutes en avance sur la réception
  est remplacée par l'heure de réception.
- `lost_events` : le total cumulé des événements que le poste a abandonnés
  sans les envoyer ; Odoo garde le plus grand total reçu.
- `config` (1.1, ignoré dans un corps 1.0) : `{"pilot": false}` d'une
  destination qui n'est pas le pilote du poste, qui ne reçoit aucun
  `config` en retour. Du pilote, `{"pilot": true, "revision_applied",
  "current", "result", "choice"}` : `current` les quatre réglages tels que
  le fichier les porte, null quand absents ou invalides ; `result` l'issue
  de la dernière révision, `{"revision", "status", "reason", "at"}` avec
  `status` `applied` ou `refused` ; `choice` la réponse à la question du
  premier pilotage, `keep_local` ou `take_odoo`, envoyée une fois. Une
  valeur hors du schéma, ou un statut, une raison ou un choix inconnu, est
  un 400 `bad_request` ; une clé hors des quatre réglages est ignorée. En
  1.2, `current.key_layouts` associe l'identifiant produit de chaque
  disposition de `keymap.json` au SHA-256 de cette disposition, null
  quand le fichier n'en porte pas (au plus 128), et la raison
  `invalid:key_layouts` est connue.
- `config` de la réponse : `{"revision", "hash", "settings", "locked"}`,
  plus `ask` pendant un premier pilotage sous *Demander à l'employé*.
  `hash` est le SHA-256 du JSON canonique de `settings` (clés triées, sans
  espace), `locked` les réglages verrouillés, `ask` les réglages libres
  dont la valeur locale diffère de celle d'Odoo. En 1.2,
  `settings.key_layouts` associe l'identifiant produit de chaque deck
  branché qu'Odoo dispose à `{"keys": [{"key", "action", "icon",
  "label"}]}`, par touche croissante, `icon` et `label` seulement quand
  ils sont fixés, au plus 16 modèles ; `locked` liste alors
  `key_layouts` quand une de ces dispositions est verrouillée.
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
