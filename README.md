

# ERPLibre addons


Odoo modules developed by the [ERPLibre](https://github.com/ERPLibre/ERPLibre)
project, under the AGPL-3.0 licence. Each Odoo version has its own branch
(`12.0` to `18.0`); this branch targets **Odoo 18.0**.

ERPLibre clones this repository into
`odoo18.0/addons/ERPLibre_erplibre_addons` through its Google Repo manifest
and adds it to the addons path. Several modules expect that ERPLibre checkout
around them: its scripts, its `.venv.erplibre`, its git clones. The Python
packages the modules need are listed in `requirements.txt`.

## Modules

### DevOps and code generation

| Module | Description |
|---|---|
| `erplibre_devops` | DevOps application for ERPLibre developers: manages local, SSH and Docker workspaces, runs and logs commands, drives the code generator, plans and tracks tests, deploys to VMs or Docker, and configures systems (Nginx, PostgreSQL, systemd, Certbot). |
| `erplibre_devops_extra` | Adds no model: at installation, creates an administrator dashboard showing the developer's own workspace, the other workspaces, the deployed VMs and the systems of `erplibre_devops`. |
| `erplibre_devops_me` | Auto-configuration without data or view: at installation, discovers the local system, its ERPLibre workspaces and the hosts of the SSH configuration, then opens the DevOps interface in a browser through ERPLibre's Selenium script. |
| `erplibre_devops_sync_external_data` | Glue module, installed automatically: lets the code generation plans of `erplibre_devops` create mirror models of external data and the bindings that turn their rows into Odoo records. |
| `erplibre_odoo_cli_base` | Not installable by design: carries only a `cli/` package that adds `odoo-bin` commands — extended `db` (create, list, drop, image load and dump), i18n export, uninstallation of a module with its dependents, theme application. |

### Requirements and presentation guide

| Module | Description |
|---|---|
| `erplibre_devops_requirement` | Tracks the software requirements of an implementation project: MoSCoW level, functional domain, phase, DevSecOps stage, STRIDE threats, acceptance criteria, dependencies and the tests that prove each requirement. Ships no requirement: a project module supplies them as data. |
| `erplibre_devops_guide` | Renders the presentation page of an implementation project from records: hero with figures, sections of cards, roadmap and counts on any model, with buttons to a URL, an action or a guided tour. Ships the engine only: a project module describes its pages in data. |

### Stream Deck

| Module | Description |
|---|---|
| `erplibre_streamdeck` | Base of the inventory of the employees' Stream Decks. Holds no model and no menu yet: only the Stream Deck category and its User and Manager groups; every internal user is a Stream Deck user. |
| `erplibre_streamdeck_devops_requirement` | The requirements of the ERPLibre Stream Deck (deck programs, GNOME extension ERPLibre Home, installation, games, mobile plugin) as `erplibre_devops_requirement` data, each with the repository tests that prove it; a test runner pushes its verdict by test reference. |

### External data synchronisation

| Module | Description |
|---|---|
| `erplibre_sync_external_data` | Engine that imports xlsx and csv files into Odoo models from a JSON configuration: header validation, create or update on sync keys, change tracking per run, cross-model transformation with dry run, email notification and revert. Runs in the background through `queue_job`. |
| `erplibre_sync_external_data_spreadsheet` | Adds the uploaded spreadsheet file to a sync run, with options to pick the sheet and skip lines at the start or the end. |
| `erplibre_sync_external_data_test` | Test-only module of the sync engine: a mirror model, sync configurations, csv and xlsx fixtures and the tests that import them. Not meant for a production database. |
| `erplibre_construction_qc_demo` | Demonstration and reference of the sync chain, themed on a construction company: imports quotes, invoices and site contacts into mirror models, then links them to projects, leads, sale orders, contacts and helpdesk tickets. |
| `sync_external_model` | Compares the local database with a remote Odoo instance over RPC for chosen modules and lists the gaps: missing or uninstalled modules, other versions, missing models or fields, differing values. |

### State of the ERPLibre code

| Module | Description |
|---|---|
| `erplibre_info` | Adds an ERPLibre block to Settings › About (ERPLibre, Odoo and Python versions, commit of the checkout) and runs code in the background, including a server restart behind a double confirmation. Base of the other `erplibre_info` modules. |
| `erplibre_info_git` | Read-only snapshots of the ERPLibre code: HEAD of each repository of the manifest and its gap to the manifest, each installed module with its installed and on-disk version, which shows pending upgrades. |
| `erplibre_info_git_fetch` | For developers: server actions that write into the git clones of the checkout — fetch and rebase forks, pull the deployed code, return to a snapshot — each with a dry run, then a doubly confirmed apply, never pushing. Installs only on a server started with `--dev`. |
| `erplibre_info_developer_menu` | Glue module: adds the code snapshots, the code runs and the ERPLibre settings to the Dev menu of `developer_menu`. Installed automatically with both modules. |

### Telephony and SMS

| Module | Description |
|---|---|
| `erplibre_mobile_gateway` | `erplibre` SMS provider: an Android phone running the ERPLibre application polls Odoo over outbound HTTPS, with HMAC-signed requests, and sends the SMS through its own SIM. Tracks every send, alerts when the phone stops polling, logs calls and incoming SMS. No Odoo IAP or external aggregator. |
| `erplibre_voip_contact` | Matches the VoIP calls of `voip_oca` to their contact by the digits of the number, shows the earlier calls and SMS with the same caller, and offers to create the missing contact or write an SMS. |
| `erplibre_repondeur` | Odoo side of a voicemail for a cellular line, answering before the carrier's mailbox: settings of the external `erplibre_sip_go` service, recordings received through HMAC-signed routes, messages linked to their contact, played and marked as heard in Odoo. Off by default. |

### Signature

| Module | Description |
|---|---|
| `erplibre_user_signature` | Limits reading and writing the handwritten signature of `base_user_signature` to its owner and the administrators; reports read it as superuser. |
| `erplibre_user_signature_portal` | Lets a portal user view, draw, import or clear their own signature from My Account (`/my/account`). |

### Website

| Module | Description |
|---|---|
| `erplibre_website_brand` | Replaces the "Powered by Odoo" footer credit with an ERPLibre signature: per website, eleven styles, colours, logo, texts and link, with a live preview. Fonts ship with the module; nothing is fetched from a third party. |
| `erplibre_website_cloudflare_nginx` | From the website settings, creates the Cloudflare DNS record of the website's domain and generates the Nginx site with a Certbot certificate through an ERPLibre script run with sudo. Requires a Cloudflare API token and sudoers rules. |
| `erplibre_crm_website_generator` | Button on a CRM opportunity that creates a website for the prospect under a subdomain of a configured domain, copies chosen products and triggers the DNS and Nginx setup. Early stage: page content is not generated yet. |

### Events

| Module | Description |
|---|---|
| `erplibre_event_table` | Seats the participants of an event at rotating tables over several rounds: scored seating combinations, interactive floor plan, printed cards and table sheets or an email to each participant. |
| `event_raffle` | Prize draws for an event on an animated 3D wheel: registrations, contacts or typed-in guests take part, each draw reveals a winner and keeps a history on the event. |
| `event_raffle_survey` | Lets the completed respondents of a survey enter an event raffle instead of the registrations, each person once, optionally filtered on required answers. |

### Interface

| Module | Description |
|---|---|
| `web_menu_reorder` | Reorders the top-level menus from Settings: renumber the sequences, sort alphabetically in a chosen language, or follow an ordered list of labels. |

## Bilingual READMEs

A module documents itself in English and in French the way ERPLibre does,
with [mmg](https://github.com/ryul1206/multilingual-markdown) (Multilingual
Markdown Generator). The source is `README.base.md`; mmg generates beside it:

- `README.md`, in English, the one Odoo shows on the module form;
- `README.fr.md`, in French.

**Never edit `README.md` or `README.fr.md` of a module that has a
`README.base.md`**: the next generation overwrites them. Edit the
`README.base.md`, then generate, and commit the three files together.

### The source file

It opens with this header, which tells mmg the languages and the one that
takes the file name without a suffix:


```markdown
<!---------------------------->
<!-- multilingual suffix: en, fr -->
<!-- no suffix: en -->
<!---------------------------->
```


The text then alternates language blocks, each opened by a marker on its own
line: `<!-- [en] -->` for English, `<!-- [fr] -->` for French,
`<!-- [common] -->` for what both languages share, such as a code example. A
block runs until the next marker. Write the two languages in the same order,
section by section: the generated files are read side by side.

### Generating

From the root of this repository:


```bash
./generate_readme.sh                                   # every README.base.md
./generate_readme.sh erplibre_devops_guide/README.base.md
```


The script handles the `README.base.md` of the root and of every module. It
finds mmg in this order: the `MMG` variable, the `mmg` of the `PATH`, then the
`.venv.erplibre` of the ERPLibre checkout this repository sits in, found by
walking up the parent directories. `ERPLIBRE_HOME` names that checkout when
the repository is cloned elsewhere. ERPLibre installs mmg in `.venv.erplibre`,
from its `requirement/erplibre_require-ments.txt`.

Without the script, from the ERPLibre checkout:


```bash
source .venv.erplibre/bin/activate
mmg --yes odoo18.0/addons/ERPLibre_erplibre_addons/<module>/README.base.md
```


ERPLibre's `make doc_markdown` does not reach this repository: it leaves out
everything under `odoo*`.

### Converting a module

1. Rename the existing `README.md` to `README.base.md` (`git mv`), so the
   history follows.
2. Add the header, then put each section in an `<!-- [en] -->` block and its
   translation in an `<!-- [fr] -->` block; code examples go in
   `<!-- [common] -->` unless their comments are text to translate.
3. Generate, read both files, commit `README.base.md`, `README.md` and
   `README.fr.md`.

A module documented in `README.rst` stays as it is: Odoo reads `README.rst`
before `README.md`.
