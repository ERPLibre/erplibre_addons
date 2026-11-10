<!---------------------------->
<!-- multilingual suffix: en, fr -->
<!-- no suffix: en -->
<!---------------------------->

<!-- [common] -->

# ERPLibre addons

<!-- [en] -->

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
| `erplibre_streamdeck` | Inventory of the employees' Stream Decks: each workstation running the GNOME extension ERPLibre Home enrolls (pairing code, API key or password) and reports its decks, its deck service and their events through JSON routes authenticated by a workstation token. Every employee reads their own workstations and the decks they have held; the manager reads the whole fleet. |
| `erplibre_streamdeck_devops_requirement` | The requirements of the ERPLibre Stream Deck (deck programs, GNOME extension ERPLibre Home, installation, games, mobile plugin) as `erplibre_devops_requirement` data, in English and Canadian French, each with the repository tests that prove it; a test runner pushes its verdict by test reference. |

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

<!-- [fr] -->

Modules Odoo développés par le projet
[ERPLibre](https://github.com/ERPLibre/ERPLibre), sous licence AGPL-3.0. Chaque
version d'Odoo a sa branche (`12.0` à `18.0`) ; celle-ci vise **Odoo 18.0**.

ERPLibre clone ce dépôt dans `odoo18.0/addons/ERPLibre_erplibre_addons` par son
manifeste Google Repo et l'ajoute au chemin des addons. Plusieurs modules
attendent ce checkout ERPLibre autour d'eux : ses scripts, son
`.venv.erplibre`, ses clones git. Les paquets Python dont les modules ont
besoin sont listés dans `requirements.txt`.

## Modules

### DevOps et génération de code

| Module | Description |
|---|---|
| `erplibre_devops` | Application DevOps pour les développeurs ERPLibre : gère des espaces de travail locaux, SSH et Docker, exécute et journalise des commandes, pilote le générateur de code, planifie et suit des tests, déploie sur des VM ou Docker et configure des systèmes (Nginx, PostgreSQL, systemd, Certbot). |
| `erplibre_devops_extra` | N'ajoute aucun modèle : à l'installation, crée pour l'administrateur un tableau de bord qui affiche son espace de travail, les autres espaces, les VM déployées et les systèmes d'`erplibre_devops`. |
| `erplibre_devops_me` | Auto-configuration sans donnée ni vue : à l'installation, découvre le système local, ses espaces de travail ERPLibre et les hôtes de la configuration SSH, puis ouvre l'interface DevOps dans un navigateur par le script Selenium d'ERPLibre. |
| `erplibre_devops_sync_external_data` | Module de liaison, installé automatiquement : permet aux plans de génération de code d'`erplibre_devops` de créer des modèles miroirs de données externes et les liaisons qui transforment leurs lignes en enregistrements Odoo. |
| `erplibre_odoo_cli_base` | Non installable par conception : ne porte qu'un paquet `cli/` qui ajoute des commandes à `odoo-bin` — `db` étendu (création, liste, suppression, chargement et sauvegarde d'image), export i18n, désinstallation d'un module avec ses dépendants, application d'un thème. |

### Requis et guide de présentation

| Module | Description |
|---|---|
| `erplibre_devops_requirement` | Suit les requis logiciels d'un projet d'implantation : niveau MoSCoW, domaine fonctionnel, phase, étape DevSecOps, menaces STRIDE, critères d'acceptation, dépendances et tests qui prouvent chaque requis. Ne livre aucun requis : un module de projet les fournit en données. |
| `erplibre_devops_guide` | Rend la page de présentation d'un projet d'implantation à partir d'enregistrements : bandeau avec chiffres, sections de cartes, feuille de route et décomptes sur n'importe quel modèle, avec boutons vers une URL, une action ou une visite guidée. Ne livre que le moteur : un module de projet décrit ses pages en données. |

### Stream Deck

| Module | Description |
|---|---|
| `erplibre_streamdeck` | Inventaire des Stream Deck des employés : chaque poste qui fait tourner l'extension GNOME ERPLibre Home s'inscrit (code d'appairage, clé d'API ou mot de passe) et remonte ses decks, son service deck et leurs événements par des routes JSON authentifiées par un jeton de poste. Chaque employé lit ses postes et les decks qu'il a tenus ; le gestionnaire lit tout le parc. |
| `erplibre_streamdeck_devops_requirement` | Les requis du Stream Deck d'ERPLibre (programmes du deck, extension GNOME ERPLibre Home, installation, jeux, plugin mobile) en données d'`erplibre_devops_requirement`, en anglais et en français canadien, chacun avec les tests de dépôt qui le prouvent ; un lanceur de tests pousse son verdict par la référence du test. |

### Synchronisation de données externes

| Module | Description |
|---|---|
| `erplibre_sync_external_data` | Moteur qui importe des fichiers xlsx et csv dans des modèles Odoo selon une configuration JSON : validation des en-têtes, création ou mise à jour sur des clés de synchronisation, suivi des changements par exécution, transformation entre modèles avec simulation, avis par courriel et annulation. S'exécute en arrière-plan par `queue_job`. |
| `erplibre_sync_external_data_spreadsheet` | Ajoute le fichier tableur téléversé à une exécution, avec le choix de la feuille et des lignes à ignorer au début ou à la fin. |
| `erplibre_sync_external_data_test` | Module de test du moteur de synchronisation : un modèle miroir, des configurations, des fichiers csv et xlsx d'essai et les tests qui les importent. Pas destiné à une base de production. |
| `erplibre_construction_qc_demo` | Démonstration et référence de la chaîne de synchronisation, sur le thème d'une entreprise de construction : importe soumissions, factures et intervenants dans des modèles miroirs, puis les lie aux projets, pistes, commandes, contacts et billets d'assistance. |
| `sync_external_model` | Compare la base locale avec une instance Odoo distante par RPC pour les modules choisis et liste les écarts : modules absents ou non installés, autres versions, modèles ou champs manquants, valeurs divergentes. |

### État du code ERPLibre

| Module | Description |
|---|---|
| `erplibre_info` | Ajoute un bloc ERPLibre dans Paramètres › À propos (versions d'ERPLibre, d'Odoo et de Python, commit du checkout) et exécute du code en arrière-plan, dont un redémarrage du serveur après double confirmation. Socle des autres modules `erplibre_info`. |
| `erplibre_info_git` | Instantanés en lecture seule du code ERPLibre : HEAD de chaque dépôt du manifeste et son écart au manifeste, chaque module installé avec sa version installée et sur disque, ce qui révèle les mises à jour en attente. |
| `erplibre_info_git_fetch` | Pour les développeurs : actions serveur qui écrivent dans les clones git du checkout — fetch et rebase des forks, pull du code déployé, retour à un instantané — chacune avec un essai à blanc puis une application doublement confirmée, sans jamais pousser. S'installe seulement sur un serveur lancé avec `--dev`. |
| `erplibre_info_developer_menu` | Module de liaison : ajoute les instantanés de code, les exécutions et les paramètres ERPLibre au menu Dev de `developer_menu`. Installé automatiquement avec les deux modules. |

### Téléphonie et SMS

| Module | Description |
|---|---|
| `erplibre_mobile_gateway` | Fournisseur SMS `erplibre` : un téléphone Android qui exécute l'application ERPLibre interroge Odoo en HTTPS sortant, par des requêtes signées HMAC, et envoie les SMS par sa propre carte SIM. Suit chaque envoi, alerte quand le téléphone cesse d'interroger, journalise les appels et les SMS reçus. Ni Odoo IAP ni agrégateur externe. |
| `erplibre_voip_contact` | Rapproche les appels VoIP de `voip_oca` de leur fiche par les chiffres du numéro, montre les appels et SMS précédents avec le même correspondant, et propose de créer la fiche manquante ou d'écrire un SMS. |
| `erplibre_repondeur` | Volet Odoo d'un répondeur pour une ligne cellulaire, qui décroche avant la boîte vocale de l'opérateur : réglages du service externe `erplibre_sip_go`, enregistrements reçus par des routes signées HMAC, messages rattachés à leur fiche, écoutés et marqués comme entendus dans Odoo. Éteint par défaut. |

### Signature

| Module | Description |
|---|---|
| `erplibre_user_signature` | Limite la lecture et l'écriture de la signature manuscrite de `base_user_signature` à son propriétaire et aux administrateurs ; les rapports la lisent en superutilisateur. |
| `erplibre_user_signature_portal` | Permet à un utilisateur du portail d'afficher, de dessiner, d'importer ou d'effacer sa propre signature depuis « Mon compte » (`/my/account`). |

### Site web

| Module | Description |
|---|---|
| `erplibre_website_brand` | Remplace la mention « Powered by Odoo » du pied de page par une signature ERPLibre : par site, onze styles, couleurs, logo, textes et lien, avec aperçu en direct. Les polices sont incluses ; rien n'est chargé d'un tiers. |
| `erplibre_website_cloudflare_nginx` | Depuis les paramètres du site web, crée l'enregistrement DNS Cloudflare du domaine du site et génère le site Nginx avec un certificat Certbot par un script ERPLibre lancé avec sudo. Requiert un jeton d'API Cloudflare et des règles sudoers. |
| `erplibre_crm_website_generator` | Bouton sur une opportunité CRM qui crée un site web pour le prospect sous un sous-domaine d'un domaine configuré, copie des produits choisis et déclenche la configuration DNS et Nginx. Stade précoce : le contenu des pages n'est pas encore généré. |

### Événements

| Module | Description |
|---|---|
| `erplibre_event_table` | Place les participants d'un événement à des tables tournantes sur plusieurs rondes : combinaisons de placement évaluées, plan de salle interactif, cartes et feuilles de table imprimées ou courriel à chaque participant. |
| `event_raffle` | Tirages de prix pour un événement sur une roue 3D animée : inscrits, contacts ou invités saisis participent, chaque tirage révèle un gagnant et garde l'historique sur l'événement. |
| `event_raffle_survey` | Fait entrer dans le tirage d'un événement les répondants ayant terminé un sondage, à la place des inscrits, chaque personne une seule fois, avec un filtre optionnel sur des réponses exigées. |

### Interface

| Module | Description |
|---|---|
| `web_menu_reorder` | Réordonne les menus principaux depuis les Paramètres : renuméroter les séquences, trier par ordre alphabétique dans une langue choisie, ou suivre une liste ordonnée de libellés. |

## README bilingues

Un module se documente en anglais et en français comme le fait ERPLibre, avec
[mmg](https://github.com/ryul1206/multilingual-markdown) (Multilingual Markdown
Generator). La source est `README.base.md` ; mmg génère à côté :

- `README.md`, en anglais, celui qu'Odoo affiche sur la fiche du module ;
- `README.fr.md`, en français.

**Ne jamais modifier `README.md` ni `README.fr.md` d'un module qui a un
`README.base.md`** : la génération suivante les écrase. Modifier le
`README.base.md`, puis générer, et committer les trois fichiers ensemble.

### Le fichier source

Il s'ouvre sur cet en-tête, qui donne à mmg les langues et celle qui prend le
nom de fichier sans suffixe :

<!-- [common] -->

```markdown
<!---------------------------->
<!-- multilingual suffix: en, fr -->
<!-- no suffix: en -->
<!---------------------------->
```

<!-- [en] -->

The text then alternates language blocks, each opened by a marker on its own
line: `<!-- [en] -->` for English, `<!-- [fr] -->` for French,
`<!-- [common] -->` for what both languages share, such as a code example. A
block runs until the next marker. Write the two languages in the same order,
section by section: the generated files are read side by side.

### Generating

From the root of this repository:

<!-- [fr] -->

Le texte alterne ensuite des blocs de langue, chacun ouvert par un marqueur
seul sur sa ligne : `<!-- [en] -->` pour l'anglais, `<!-- [fr] -->` pour le
français, `<!-- [common] -->` pour ce que les deux langues partagent, comme un
exemple de code. Un bloc court jusqu'au marqueur suivant. Écrire les deux
langues dans le même ordre, section par section : les fichiers générés se
lisent côte à côte.

### Générer

Depuis la racine de ce dépôt :

<!-- [common] -->

```bash
./generate_readme.sh                                   # every README.base.md
./generate_readme.sh erplibre_devops_guide/README.base.md
```

<!-- [en] -->

The script handles the `README.base.md` of the root and of every module. It
finds mmg in this order: the `MMG` variable, the `mmg` of the `PATH`, then the
`.venv.erplibre` of the ERPLibre checkout this repository sits in, found by
walking up the parent directories. `ERPLIBRE_HOME` names that checkout when
the repository is cloned elsewhere. ERPLibre installs mmg in `.venv.erplibre`,
from its `requirement/erplibre_require-ments.txt`.

Without the script, from the ERPLibre checkout:

<!-- [fr] -->

Le script traite le `README.base.md` de la racine et de chaque module. Il
trouve mmg dans cet ordre : la variable `MMG`, le `mmg` du `PATH`, puis le
`.venv.erplibre` du checkout ERPLibre qui contient ce dépôt, trouvé en
remontant les répertoires parents. `ERPLIBRE_HOME` désigne ce checkout quand
le dépôt est cloné ailleurs. ERPLibre installe mmg dans `.venv.erplibre`,
d'après son `requirement/erplibre_require-ments.txt`.

Sans le script, depuis le checkout ERPLibre :

<!-- [common] -->

```bash
source .venv.erplibre/bin/activate
mmg --yes odoo18.0/addons/ERPLibre_erplibre_addons/<module>/README.base.md
```

<!-- [en] -->

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

<!-- [fr] -->

Le `make doc_markdown` d'ERPLibre n'atteint pas ce dépôt : il écarte tout ce
qui se trouve sous `odoo*`.

### Convertir un module

1. Renommer le `README.md` existant en `README.base.md` (`git mv`), pour que
   l'historique suive.
2. Ajouter l'en-tête, puis mettre chaque section dans un bloc `<!-- [en] -->`
   et sa traduction dans un bloc `<!-- [fr] -->` ; les exemples de code vont
   dans `<!-- [common] -->`, sauf si leurs commentaires sont du texte à
   traduire.
3. Générer, relire les deux fichiers, committer `README.base.md`, `README.md`
   et `README.fr.md`.

Un module documenté en `README.rst` reste tel quel : Odoo lit `README.rst`
avant `README.md`.
