# TODO — erplibre_sync_external_data

## 1. Bug — `isinstance(value, fields.datetime)` incorrect

**Fichier** : `models/sync_data_exec.py:744`

`fields.datetime` est un descripteur Odoo, pas un `datetime` Python. Le check est toujours `False`
quand la valeur vient d'openpyxl, donc `_transform_date` est appelé sur des valeurs déjà parsées.

```python
# ACTUEL (bug)
if not isinstance(value, fields.datetime):

# CORRECT
if not isinstance(value, (date, datetime)):
```

---

## 2. Danger — `env.cr.commit()` en milieu de transaction

**Fichier** : `models/sync_data_exec.py:673`

```python
def _link_tracking_values(self, ...):
    self.env.cr.commit()
```

Bloque tout rollback ultérieur. Si une exception survient après ce commit, les données partielles
sont persistées définitivement. Avec `queue_job` (job rejoué), le risque de données dupliquées est réel.
À supprimer — le tracking doit vivre dans la même transaction que l'upsert.

---

## 3. Architecture — `rec.file` non déclaré dans le modèle

**Fichier** : `models/sync_data_exec.py:289,292,298`

`action_import_default_algo` accède à `rec.file` mais aucun champ `file` n'est déclaré dans
`SyncDataExec`. Le module compagnon `erplibre_sync_external_data_spreadsheet` semble le fournir,
mais la dépendance n'est pas dans le manifest. Le module plante si ce module compagnon est absent.

Deux options :
- Déclarer la dépendance dans `__manifest__.py`
- Déclarer le champ directement dans ce module

---

## 4. État machine trop limité

**Fichier** : `models/sync_data_exec.py:33-40`

Seulement `"upload"` et `"summary"`. États manquants :

| État | Utilité |
|------|---------|
| `"processing"` | Pendant le job async, empêche les doubles soumissions |
| `"error"` | Quand `has_error = True` — actuellement invisible en vue liste |

Les champs `has_error` / `has_error_msg` existent mais ne sont jamais écrits dans les chemins
de code visibles.

---

## 5. Méthode vide avec `@api.depends` actif

**Fichier** : `models/sync_data_transform.py:73-75`

```python
@api.depends("context_name")
def _compute_context_name(self):
    pass
```

Le `@api.depends` déclenche un recalcul à chaque changement de `context_name` pour rien.
Retirer le décorateur si la méthode est un hook pour modules enfants, ou supprimer la méthode.

---

## 6. Niveaux de log incorrects

**Fichier** : `models/sync_data_exec.py:769,779`

```python
_logger.error("Detect int %s from char %s", cleaned, value)
_logger.error("Detect float %s from char %s", cleaned, value)
```

La conversion réussit — ce ne sont pas des erreurs. Remplacer par `_logger.warning`.

---

## 7. Fonctionnalités annoncées mais non implémentées

**Fichiers** : `models/sync_data_transform.py:345-350`, `models/sync_data_transform_exec.py`

Les bindings `many2many`, `one2many` et la mise à jour de records existants sont silencieusement
ignorés avec un `_logger.warning`. Une `UserError` explicite ou une documentation dans le champ
`help` éviterait les configurations inutiles et le debugging difficile.

Cas concernés :
- `many2many`/`one2many` binding dans `_bind_transform`
- `one2many` write-back dans `action_write_modification`
- Mise à jour de record existant dans `_bind_transform_model`

---

## 8. Contrainte implicite non documentée sur `file_no_line`

**Fichier** : `models/sync_data_exec.py:645-651`

```python
matching = [r for r in model_record_id if r.file_no_line == file_no_line]
```

En cas de doublons sur les champs `sync`, le modèle cible doit avoir un champ `file_no_line`.
Cette contrainte n'est ni vérifiée ni documentée. Sans ce champ, comportement inattendu ou
`AttributeError` silencieuse.

À faire : vérifier l'existence du champ en début d'extraction, ou documenter la contrainte
dans `sync.model`.
