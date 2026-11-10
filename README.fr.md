

# ERPLibre addons


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


```markdown
<!---------------------------->
<!-- multilingual suffix: en, fr -->
<!-- no suffix: en -->
<!---------------------------->
```


Le texte alterne ensuite des blocs de langue, chacun ouvert par un marqueur
seul sur sa ligne : `<!-- [en] -->` pour l'anglais, `<!-- [fr] -->` pour le
français, `<!-- [common] -->` pour ce que les deux langues partagent, comme un
exemple de code. Un bloc court jusqu'au marqueur suivant. Écrire les deux
langues dans le même ordre, section par section : les fichiers générés se
lisent côte à côte.

### Générer

Depuis la racine de ce dépôt :


```bash
./generate_readme.sh                                   # every README.base.md
./generate_readme.sh erplibre_devops_guide/README.base.md
```


Le script traite le `README.base.md` de la racine et de chaque module. Il
trouve mmg dans cet ordre : la variable `MMG`, le `mmg` du `PATH`, puis le
`.venv.erplibre` du checkout ERPLibre qui contient ce dépôt, trouvé en
remontant les répertoires parents. `ERPLIBRE_HOME` désigne ce checkout quand
le dépôt est cloné ailleurs. ERPLibre installe mmg dans `.venv.erplibre`,
d'après son `requirement/erplibre_require-ments.txt`.

Sans le script, depuis le checkout ERPLibre :


```bash
source .venv.erplibre/bin/activate
mmg --yes odoo18.0/addons/ERPLibre_erplibre_addons/<module>/README.base.md
```


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