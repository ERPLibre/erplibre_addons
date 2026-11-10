

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
  uuid and the time it was observed. A uuid already stored is acknowledged
  again without change, so a report sent again creates nothing. A time
  more than 5 minutes ahead of the reception is replaced by the reception
  time.
- `lost_events`: the running total of events the workstation dropped
  unsent; Odoo keeps the largest total received.
- A deck is known by its serial number, key `sn:<serial>`; a deck without
  a readable serial number is known by its workstation, product id and
  USB path, key `nosn:<workstation>:<product>:<path>`, and is never
  merged with a deck of another workstation. A serial outside
  `[A-Za-z0-9._-]{1,64}` is a 400 `bad_request`: having no `:`, it can
  never name a deck without serial.

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
