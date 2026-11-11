

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
  unenrolled ». Closing does not depend on the Settings: an activity
  opened before they were disabled still closes.
- **Archived manager.** When the named manager is archived later, only
  the employee part opens, and each run of the cron writes a warning to
  the log, which names nobody.
- **Access.** An activity is read with its record. An employee reads the
  activities of their workstations, the manager's included, and those of
  the decks they hold or held, from their first holding on, plus those
  assigned to them; never those of another employee's workstation. On a
  workstation's thread, the employee posts, edits their own messages and
  closes their own activities; only a manager edits, closes or deletes
  those of others. Only the monitoring creates activities of its four
  types.
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
