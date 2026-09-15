# ERPLibre Construction QC — external-sync demo

A complete, installable **example** of the ERPLibre external-data-sync chain
(`erplibre_sync_external_data`), themed around a Québec construction company
tracking *chantiers* (job sites). It is the reference output of the
code-generator's external-sync feature (see `doc/CODE_GENERATOR.md` →
*Generate external sync*) and reproduces, in one module, the functionality of
the real consumer modules (safirh, project_bpr, the FCI helpdesk mirror,
`erplibre_sync_external_data_project`).

## What it demonstrates

| Capability | Where |
|---|---|
| xlsx + csv import into mirror models + header **value-maps** | `data/sync_model.xml`, `models/construction_doc_*.py` |
| Declarative cross-model **bind** → `project.project` | `sync_model_construction_doc_soumission` |
| Project **budget aggregates** (computed) | `models/project_project.py` |
| Custom transform **context** + no-match JSON + **helpdesk opt-out** | `models/sync_data_transform.py`, `models/helpdesk_ticket.py` |
| **`method_call`** devis binding → `crm.lead` + `sale.order` + lines, **staged** | `action_transform_construction_devis` |
| Intervenant → **`res.partner`**, **staged** (`method_call`) | `action_transform_construction_intervenant` |
| `method_call` **staging** via `sync.data.transform.exec` + `#REPLACE` deps | `_stage_exec`, `action_write_all` |
| **queue_job** ticket → chantier matcher | `action_match_chantier_tickets` |
| **`account.move`** → chantier auto-link (computed) | `models/account_move.py` |
| Geo **coordinates** imported → `latitude`/`longitude` (Leaflet-ready) | `construction.doc_soumission`, *Coordonnées* column |
| **Views + menus generated** by erplibre_devops (not hand-written) | `views/*.xml`, `tools/regenerate_views.py` |

## Models

- `construction.doc_soumission` (xlsx, sheet *Soumissions*) — quotes.
- `construction.doc_facture` (csv) — invoices.
- `construction.doc_intervenant` (csv) — site contacts → `res.partner`.
- `construction.doc_devis` (csv, `method_call`) — quotes → CRM/sale.
- extends `project.project` (`no_chantier`, `is_chantier`, budgets),
  `sale.order` / `account.move` (chantier link), `helpdesk.ticket`
  (opt-out + chantier link), `sync.data.transform` (context + matcher).

## Run the tests

```bash
make test_addons_construction_qc_demo
```

The tests import the committed fixtures (`tests/data/Suivi-Chantiers.xlsx`,
`Factures.csv`, `Intervenants.csv`, `Devis.csv`) through the sync engine and
assert the mirror rows + the transform results. Both the declarative
`bind_field_model` binds and the `method_call` binds now **stage**
`sync.data.transform.exec` rows (a validation step); `action_write_all()`
applies them, resolving `#REPLACE.<token>` parent→child dependencies.

## Regenerate the views

The `views/*.xml` + `views/menu.xml` are produced by the code generator
(`erplibre_devops`), not hand-written. To regenerate after a model change, see
`tools/regenerate_views.py` (drives `code.generator.generate.views.wizard` →
`code.generator.writer` against the installed models into a temp dir; the
output is then integrated here).

> Dependencies: `erplibre_sync_external_data_spreadsheet`, `project`, `sale`,
> `account`, `helpdesk_mgmt`, `mail`. License AGPL-3.
