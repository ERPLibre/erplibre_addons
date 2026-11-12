

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
revision, and keeps there the layouts of the models Odoo does not send.
A model that no layer lays out keeps the automatic layout of the deck
program.

Each workstation gets the layouts within the catalog of its own report,
since it refuses the whole revision for a key its deck program cannot
lay out: a model that catalog does not describe gets no layout, a key
past its number of keys is left out, an action it lacks goes as a black
key, as the deck program would show it, and an icon it lacks is left
out. A report without a catalog gets no layout; its settings still go.

The catalog (*Configuration › Catalog*) is the union of what the
workstations report: the actions, the icons and the geometry of each
deck model. An item that no workstation reports any more stays, with the
date it was last seen, to the hour. The geometry of a model is a constant
of its hardware: a model of the table shipped with the module takes the
table's, and a model outside it keeps the geometry first reported. No
report changes it, so no workstation decides the keys Odoo lays out for
the others.

A layout changed in the file after its revision was applied is handled
as a setting, by the SHA-256 of each model's layout (canonical JSON: keys
sorted, no space, every character outside ASCII escaped as `\uXXXX`):

- a **free** layout becomes a layout of the workstation marked *Kept in
  the workstation's file*, with the source *Workstation file*, and Odoo
  sends no layout for that model any more; creating or changing one of
  its keys sends it again;
- a **locked** layout, or one removed from the file, is offered again.

The first-pilot question covers the free layouts as the free settings:
a free layout of the file whose hash differs from Odoo's puts
`key_layouts` in `ask`, unless one of the sent layouts is locked, and
keeping the local values adopts it as above. A workstation piloted before
protocol 1.2 has made its choice already: a layout then follows the rule
of a setting newly managed, offered under a new revision.

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
  differs from Odoo's, `key_layouts` included. In 1.2,
  `settings.key_layouts` maps the product id of each connected deck that
  Odoo lays out, within the catalog of the report, to `{"keys": [{"key",
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
