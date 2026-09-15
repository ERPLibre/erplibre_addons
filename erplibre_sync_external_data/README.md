# Sync External Data

**Version**: 18.0.1.2.4 | **Licence**: AGPL-3 | **Auteur**: TechnoLibre

Importe et synchronise des données depuis des fichiers externes (`.xlsx`, `.csv`) vers des modèles Odoo. Gère la création, la mise à jour, le suivi des changements, la transformation cross-modèle et la réversion.

## Fonctionnalités

- Import de fichiers `.xlsx` et `.csv` avec validation des en-têtes
- Création ou mise à jour (upsert) de records Odoo via des champs de synchronisation configurables
- Suivi des modifications et créations liées à chaque exécution
- Transformation en deux phases : extraction puis liaison cross-modèle
- Traitement asynchrone via OCA `queue_job`
- Notifications email aux abonnés à la réception de changements
- Réversion des modifications (annulation d'un sync)
- Mode dry-run pour la transformation (prévisualisation sans écriture)
- Parsing de dates : formats ISO, FR, EN, abréviations françaises (janv, févr, etc.)

## Dépendances

**Modules Odoo** : `mail`, `queue_job`

**Python** : `openpyxl`, `pdfminer.six`

## Modèles

| Modèle | Description |
|--------|-------------|
| `sync.model` | Template de configuration d'un sync (nom, modèle cible, métadonnées JSON) |
| `sync.data.exec` | Exécution principale : reçoit le fichier, lance l'extraction et la transformation |
| `sync.data.create` | Trace les records créés lors d'une exécution |
| `sync.data.transform` | Étape de transformation : liaison de références cross-modèle |
| `sync.data.transform.exec` | Opération unitaire de transformation (create ou write sur un modèle) |
| `sync.data.transform.filter_search` | Patterns de filtrage utilisés pendant la transformation |
| `sync.data.exec.cron.log` | Logs d'exécutions planifiées |

## Workflow

```
1. Configurer sync.model      → JSON métadonnées (en-têtes, champs, filetype…)
2. Créer sync.data.exec       → Attacher le fichier, sélectionner les templates
3. Lancer action_process_sync_data_async
       ↓
   Extraction du fichier     → lecture ligne par ligne, validation des en-têtes
       ↓
   Upsert des records        → create ou write selon les champs sync
       ↓
   Suivi des changements     → mail.tracking.value liés à l'exécution
       ↓
4. (Optionnel) action_process_transform_async
       ↓
   sync.data.transform       → résolution de dépendances cross-modèle
       ↓
   sync.data.transform.exec  → exécution des create/write avec dépendances résolues
       ↓
5. action_revert_data         → annuler les changements si nécessaire
```

## Configuration — spreadsheet_extraction_metadata

Le champ `spreadsheet_extraction_metadata` de `sync.model` est un JSON qui pilote l'extraction.

### Structure minimale

```json
{
    "filetype": "xlsx",
    "sheet_name": "Feuil1",
    "index_line_header": 1,
    "nb_line_header": 1,
    "header": [
        ["Colonne A", "field_name_a"],
        ["Colonne B", "field_name_b", {"valeur_source": "valeur_odoo"}]
    ],
    "sync": ["field_name_a"]
}
```

### Paramètres disponibles

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `filetype` | `str` | `""` | `"xlsx"` ou `"csv"` |
| `sheet_name` | `str` | `""` | Nom de la feuille xlsx |
| `index_line_header` | `int` | `0` | Numéro de ligne des en-têtes (1-based pour xlsx) |
| `nb_line_header` | `int` | `1` | Nombre de lignes d'en-têtes (multi-ligne : valeurs concaténées) |
| `header` | `list` | `[]` | Liste de `[nom_colonne, nom_champ]` ou `[nom_colonne, nom_champ, {valeur_map}]` |
| `sync` | `list` | `[]` | Champs utilisés comme clés d'upsert |
| `ignore_last_line` | `int` | `0` | Nombre de lignes à ignorer en fin de fichier |
| `index_last_line` | `int` | `0` | Indice de dernière ligne à traiter (0 = toutes) |
| `ignore_data` | `list` | `[]` | Valeurs à remplacer par `False` |
| `ignore_validation_header` | `bool` | `false` | Désactiver la validation des en-têtes |
| `callback_init_read_header` | `str` | `null` | Nom de méthode appelée après lecture des en-têtes |
| `option_level.repeat_column` | `list` | `[]` | Indices de colonnes qui déclenchent la répétition de ligne |
| `option_level.duplicate_column_when_empty` | `list` | `[]` | Indices de colonnes dont la valeur est bufférisée quand vide |
| `bind` | `list` | `[]` | Configurations de liaison pour la phase de transformation |

### Exemples d'options avancées

```json
{
    "option_level": {
        "repeat_column": [0, 1],
        "duplicate_column_when_empty": [2]
    }
}
```

- **`repeat_column`** : si les colonnes listées sont vides, la ligne est ignorée et les valeurs sont héritées de la ligne précédente où ces colonnes étaient remplies.
- **`duplicate_column_when_empty`** : si la cellule est vide, la dernière valeur non-vide de cette colonne est réutilisée.

## Formats de date supportés

Le module parse automatiquement les formats suivants (séparateurs `/` ou `-`) :

| Format | Exemple |
|--------|---------|
| `dd/mm/yyyy` | `15/03/2024` |
| `yyyy/mm/dd` | `2024/03/15` |
| `dd/MMM/yy` | `15/Mar/24` |
| `dd/mm/yy` | `15/03/24` |
| `mm/dd/yy` (US) | `01/25/24` |
| Année seule (int) | `2024` → `2024-01-01` |
| Abréviations FR | `15/janv/24`, `10-févr-24`, `25/déc/24` |

Abréviations françaises reconnues : `janv`, `févr`, `fevr`, `fév`, `mars`, `avr`, `mai`, `juin`, `juil`, `août`, `aout`, `sept`, `oct`, `nov`, `déc`, `dec`.

## Sécurité

| Groupe | Description |
|--------|-------------|
| `group_erplibre_sync_external_data_exec_notify` | Reçoit les notifications email lors de changements |

Les utilisateurs de ce groupe sont automatiquement abonnés aux exécutions et reçoivent un email récapitulatif si des records ont été créés ou modifiés.

## Jobs asynchrones (queue_job)

| Méthode | Modèle | Description |
|---------|--------|-------------|
| `action_process_sync_data` | `sync.data.exec` | Extraction + upsert du fichier |
| `action_transform` | `sync.data.transform` | Transformation cross-modèle |
| `queue_ticket_to_transform` | `sync.data.transform` | Mise en file de tickets de transformation |
| `queue_end_transform` | `sync.data.transform` | Finalisation de la transformation |

Si `queue_job` n'est pas chargé au démarrage, les jobs s'exécutent de façon synchrone.

## Réversion

```python
sync_exec.action_revert_data()
```

Remet les champs modifiés à leur valeur précédente en lisant les `mail.tracking.value` liés à l'exécution. Champs supportés : `date`, `datetime`, `int`, `float`, `monetary`, `char`, `text`.

## Tests

```bash
./run.sh -d test --log-level=test --test-enable --stop-after-init \
    -i erplibre_sync_external_data
```

Les tests couvrent :
- Parsing de dates (30+ cas : formats ISO, FR, EN, accents, cas limites)
- Calcul de durée d'exécution
- Création/mise à jour via `sync.data.transform.exec`
- Compteurs de modifications et créations
- Gestion du `has_data_to_write` et `data_was_wrote`

## Structure du module

```
erplibre_sync_external_data/
├── models/
│   ├── sync_data_exec.py              # Extraction, upsert, parsing
│   ├── sync_data_transform.py         # Transformation cross-modèle
│   ├── sync_data_transform_exec.py    # Opérations unitaires de transformation
│   ├── sync_data_transform_filter_search.py
│   ├── sync_data_create.py            # Trace des records créés
│   ├── sync_data_exec_cron_log.py     # Logs cron
│   ├── sync_model.py                  # Template de configuration
│   └── mail_tracking_value.py         # Extension pour lier tracking à l'exécution
├── views/                             # Vues list/form pour tous les modèles
├── security/                          # Groupes et ACL
├── data/                              # Templates mail, canaux et fonctions queue_job
├── migrations/                        # Scripts de migration (18.0.1.1.0 → 18.0.1.2.4)
└── tests/                             # Tests unitaires
```
