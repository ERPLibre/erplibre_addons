# ERPLibre DevOps

Module Odoo pour la gestion DevOps d'ERPLibre : workspaces, génération de code,
tests, déploiement, monitoring et intégration IA.

**Version** : 18.0.1.0.0
**Licence** : AGPL-3
**Auteur** : Mathieu Benoit
**Catégorie** : Tools

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Modèles de données](#modèles-de-données)
- [Pipeline DevOps](#pipeline-devops)
- [Dépendances](#dépendances)
- [Installation](#installation)
- [Configuration](#configuration)
- [Pistes d'amélioration](#pistes-damélioration)

## Vue d'ensemble

Le module `erplibre_devops` implémente un pipeline DevOps complet directement
dans Odoo, couvrant les 8 phases du cycle de vie logiciel :

```
Plan → Code → Build → Test → Release → Deploy → Operate → Monitor
```

Il permet de :

- **Gérer des workspaces** de développement (locaux, SSH, Docker)
- **Générer du code** Odoo via le système Code Generator
- **Exécuter et tracer** des commandes avec capture stdout/stderr
- **Planifier des tests** et suivre leurs résultats
- **Déployer** sur des VMs (VirtualBox, Qemu/KVM) ou via Docker
- **Configurer** des systèmes (Nginx, PostgreSQL, Systemd, Certbot, Cloudflare)
- **Générer du contenu** via LocalAI (texte, images, son)
- **Intégrer des IDEs** (PyCharm, breakpoints Python)

## Architecture

```
erplibre_devops/
├── __init__.py
├── __manifest__.py
├── hooks.py                         # Post-install : init système, workspace "me"
├── models/                          # 65 fichiers de modèles
│   ├── devops_workspace.py          # Workspace central (~1989 lignes)
│   ├── devops_system.py             # Gestion système local/distant (~2605 lignes)
│   ├── devops_cg_new_project.py     # Projets de génération de code (~1826 lignes)
│   ├── devops_exec.py               # Suivi d'exécution de commandes
│   ├── devops_plan_project.py       # Planification de projets avec IA
│   ├── devops_operate_localai.py    # Intégration LocalAI
│   ├── devops_deploy_vm.py          # Déploiement sur VMs
│   ├── devops_docker_*.py           # Gestion Docker (compose, image, container, etc.)
│   ├── devops_cg_*.py               # Code Generator (module, model, field)
│   ├── devops_test_*.py             # Framework de test (plan, case, result)
│   ├── devops_ide_*.py              # Intégration IDE (PyCharm, breakpoints)
│   ├── devops_system_*.py           # Config système (nginx, postgres, systemd, etc.)
│   ├── erplibre_mode*.py            # Modes ERPLibre (env, exec, source, version)
│   └── ...
├── views/                           # ~65 fichiers de vues XML
├── wizards/                         # Wizard multi-étapes pour actions planifiées
│   ├── devops_plan_action_wizard.py # (~2437 lignes)
│   └── devops_plan_action_wizard.xml
├── data/                            # 26 fichiers de données initiales
├── security/
│   └── ir.model.access.csv          # 57 règles d'accès
└── static/description/
    ├── icon.png
    └── devops_plan.png
```

## Modèles de données

### Workspace (coeur du module)

| Modèle | Description |
|--------|-------------|
| `devops.workspace` | Workspace de développement — point central reliant tous les composants |
| `devops.workspace.docker` | Configuration Docker d'un workspace |
| `devops.workspace.terminal` | Sessions terminal liées au workspace |
| `devops.workspace.config.conf` | Fichiers de configuration du workspace |

Le workspace est le hub central : il référence les projets CG, les exécutions,
les tests, les connexions SSH, les images DB, les conteneurs Docker et les
breakpoints IDE.

### Génération de code (Code Generator)

| Modèle | Description |
|--------|-------------|
| `devops.cg` | Projet de génération de code |
| `devops.cg.module` | Module Odoo à générer |
| `devops.cg.model` | Modèle ORM à générer (avec tracking de champs) |
| `devops.cg.field` | Définition de champ (16 types supportés) |
| `devops.cg.new.project` | Assistant de création de nouveau projet CG |
| `devops.cg.new.project.stage` | Étapes du pipeline de création |
| `devops.cg.test.case` | Cas de test pour la génération de code |

Hiérarchie : **CG → Module → Model → Field**, avec propagation d'erreurs
depuis les champs vers les modèles.

Types de champs supportés : `char`, `text`, `html`, `json`, `binary`,
`integer`, `float`, `boolean`, `date`, `datetime`, `many2one`,
`many2onereference`, `many2many`, `one2many`, `selection`, `monetary`.

### Exécution et traçabilité

| Modèle | Description |
|--------|-------------|
| `devops.exec` | Exécution de commande (stdin/stdout/stderr, durée, statut) |
| `devops.exec.bundle` | Groupe d'exécutions liées |
| `devops.exec.error` | Erreur d'exécution |
| `devops.log.error` | Entrée de log d'erreur (extraite automatiquement) |
| `devops.log.warning` | Entrée de log d'avertissement |
| `devops.log.makefile.target` | Log de cible Makefile |
| `devops.instance.exec` | Exécution d'instance |

Le système parse automatiquement les logs pour extraire erreurs et
avertissements par mots-clés.

### Tests

| Modèle | Description |
|--------|-------------|
| `devops.test.plan` | Plan de test (suite) |
| `devops.test.case` | Cas de test individuel |
| `devops.test.case.exec` | Exécution d'un cas de test |
| `devops.test.plan.exec` | Exécution d'un plan de test |
| `devops.test.result` | Résultat de test |

### Déploiement

| Modèle | Description |
|--------|-------------|
| `devops.deploy.vm` | Machine virtuelle (VirtualBox, Qemu/KVM) |
| `devops.deploy.vm.exec` | Exécution sur VM |
| `devops.deploy.vm.exec.stage` | Étape d'exécution VM |
| `devops.deploy.vm.snapshot` | Snapshot de VM |
| `devops.docker.compose` | Configuration Docker Compose |
| `devops.docker.image` | Image Docker |
| `devops.docker.container` | Conteneur Docker |
| `devops.docker.network` | Réseau Docker |
| `devops.docker.volume` | Volume Docker |
| `devops.docker.compose.template` | Template Docker Compose |

### Système et configuration

| Modèle | Description |
|--------|-------------|
| `devops.system` | Système local ou distant (SSH, terminal, processus) |
| `devops.system.nginx.site.conf` | Configuration Nginx |
| `devops.system.nginx.site.conf.template` | Template Nginx |
| `devops.system.postgres.conf` | Configuration PostgreSQL |
| `devops.system.systemd.service.conf` | Service Systemd |
| `devops.system.certbot.conf` | Certificat SSL (Certbot) |
| `devops.system.cloudflare.conf` | Configuration DNS Cloudflare |
| `devops.db.image` | Image/backup de base de données |

### Planification et IA

| Modèle | Description |
|--------|-------------|
| `devops.plan.project` | Projet planifié (génération web, contenu IA) |
| `devops.plan.project.pptx` | Génération de présentations PowerPoint |
| `devops.plan.cg` | Planification de génération de code |
| `devops.operate.localai` | Opérations LocalAI (texte, image, son) |
| `devops.code.todo` | Suivi de TODO dans le code |

### Configuration ERPLibre

| Modèle | Description |
|--------|-------------|
| `erplibre.mode` | Mode d'exécution ERPLibre |
| `erplibre.mode.env` | Mode d'environnement (dev/test/prod) |
| `erplibre.mode.exec` | Mode d'exécution |
| `erplibre.mode.source` | Type de source |
| `erplibre.mode.version.base` | Version Odoo |
| `erplibre.mode.version.erplibre` | Version ERPLibre |
| `erplibre.config.path.home` | Chemin home configurable |

### Génération d'images et IDE

| Modèle | Description |
|--------|-------------|
| `devops.gen.img.detail` | Niveau de détail pour génération d'images |
| `devops.gen.img.light` | Style d'éclairage |
| `devops.gen.img.style.artist` | Style artistique |
| `devops.gen.img.style.type` | Type de style |
| `devops.gen.img.texture` | Texture |
| `devops.ide.breakpoint` | Breakpoints Python |
| `devops.ide.pycharm` | Intégration PyCharm |
| `devops.ide.pycharm.configuration` | Configuration PyCharm |

## Pipeline DevOps

### Plan — Planifier et définir

Planification de projets avec assistance IA (LocalAI). Génération de sites
web one-pager, contenu alimentaire/santé/boutique, présentations PowerPoint.

### Code — Développer

Génération de modules Odoo via le Code Generator. Création hiérarchique :
projet → module → modèle → champ. Intégration IDE avec breakpoints Python
et configuration PyCharm.

### Build — Package

Gestion des images de base de données, templates Docker Compose, et
construction d'images Docker.

### Test — Tester

Plans de test avec cas de test individuels. Suivi d'exécution et résultats.
Intégration avec le Code Generator pour valider le code généré.

### Release — Livrable

Gestion des versions et suivi des livrables (en cours de développement).

### Deploy — Déploiement

Déploiement sur VMs (VirtualBox, Qemu/KVM) avec gestion de snapshots.
Déploiement Docker via Docker Compose. Configuration automatique de
Nginx, Systemd, Certbot (SSL), Cloudflare (DNS).

### Operate — Opération

Intégration LocalAI pour génération de texte (Mistral OpenOrca), images
et son (TTS). Suivi des instances en production.

### Monitor — Surveillance

Traçabilité complète des exécutions avec capture stdout/stderr, parsing
automatique des erreurs/avertissements, durée et codes de statut.

## Dépendances

### Modules Odoo requis

- `code_generator` — Moteur de génération de code
- `code_generator_cron` — Génération de tâches planifiées
- `code_generator_db_servers` — Génération de config DB
- `code_generator_geoengine` — Support géospatial
- `code_generator_hook` — Hooks de génération
- `code_generator_portal` — Génération de portail
- `code_generator_theme_website` — Thèmes de sites web
- `code_generator_website_leaflet` — Cartes Leaflet
- `code_generator_website_snippet` — Snippets de site web
- `mail` — Activités et chatter
- `multi_step_wizard` — Wizards multi-étapes
- `queue_job` — Exécution asynchrone de tâches

### Bibliothèques Python

- `paramiko` — Connexions SSH
- `subprocess` — Exécution de processus locaux

## Installation

1. S'assurer que les modules dépendants sont disponibles dans le addons path
2. Installer le module via l'interface Odoo ou en ligne de commande :

```bash
./run.sh -d ma_base -i erplibre_devops
```

Le hook post-installation (`hooks.py`) effectue automatiquement :

- Initialisation du système local
- Rafraîchissement des images de base de données
- Configuration du type de notification admin en "inbox"
- Création du workspace "me"
- Auto-détection du terminal et de la commande de recherche

## Configuration

### config.conf (obligatoire)

```ini
server_wide_modules = base,web,queue_job
```

### config.conf (facultatif)

```ini
workers = 2

[queue_job]
channels = root:2
```

### Paramètres système

Via **Configuration > Paramètres** :

- **Terminal par défaut** : gnome-terminal, xterm, etc. (auto-détecté)
- **Commande de recherche** : locate, find (auto-détecté)

## Pistes d'amélioration

### Sécurité (Critique)

1. **Mots de passe en ligne de commande** — `sshpass -p {password}` expose le
   mot de passe dans `ps aux`. Utiliser `sshpass -f` avec un fichier temporaire
   ou migrer vers l'authentification par clé SSH exclusivement.

2. **Mots de passe hardcodés** — `mysecretpassword` et `admin` dans les
   templates Docker Compose (`devops_workspace_docker.py`). Utiliser des
   variables d'environnement ou `ir.config_parameter`.

3. **Injection shell** — `subprocess.Popen` avec `shell=True` et interpolation
   de chaînes non échappées (`devops_system.py`). Utiliser des listes
   d'arguments et `shell=False`, ou `shlex.quote()` pour les valeurs
   dynamiques.

4. **Vérification SSH désactivée** — `AutoAddPolicy()` et
   `StrictHostKeyChecking=no` ouvrent la porte aux attaques MITM. Implémenter
   un stockage de clés hôtes et une validation.

### Qualité de code (Haute)

5. **Fichiers trop volumineux** — `devops_system.py` (2605 lignes),
   `devops_plan_action_wizard.py` (2437 lignes), `devops_workspace.py` (1989
   lignes). Découper en sous-modules thématiques (ex: `devops_system_ssh.py`,
   `devops_system_process.py`, `devops_system_config.py`).

6. **Bare except** — `devops_ide_breakpoint.py:161` attrape `SystemExit` et
   `KeyboardInterrupt`. Remplacer par `except (ValueError, TypeError):`.

7. **Exceptions silencieuses** — `except Exception: pass` dans le wizard
   (ligne 2238) masque les erreurs. Au minimum logger l'exception.

8. **Docstrings manquantes** — 70+ méthodes publiques sans docstring dans les
   fichiers principaux. Ajouter au minimum une ligne de description.

### Maintenabilité (Moyenne)

9. **90+ TODO non résolus** — Prioriser et résoudre ou créer des issues de
   suivi. Certains TODO concernent des problèmes de sécurité (ex: validation
   d'AuthenticationException).

10. **Pas de groupes de sécurité** — Tous les modèles donnent CRUD complet à
    `base.group_user`. Créer des groupes spécifiques (ex: `devops_manager`,
    `devops_user`) avec des permissions différenciées.

11. **Parsing fragile** — Configuration traitée par manipulation de chaînes au
    lieu de `configparser` (`devops_workspace_docker.py:251`).

12. **API dépréciée** — `subprocess.Popen()` au lieu de `subprocess.run()` pour
    les exécutions simples de commandes.

13. **Imports inutilisés** — `import time` dans `devops_system.py`, `from odoo
    import tools` dans `devops_cg_new_project.py`.

### Fonctionnalités incomplètes

14. **Technopoïèse** — Plusieurs fonctionnalités marquées MISSING dans le
    concept d'auto-génération : refactor, publish, reverse, data, plan,
    operate, monitor, deploy, release, test, doc.

15. **Cron commenté** — `data/ir_cron.xml` est commenté dans le manifest,
    indiquant une fonctionnalité de tâches planifiées désactivée.

16. **Support macOS incomplet** — TODO pour `mdfind` dans
    `devops_system.py:190`.
