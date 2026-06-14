# regenerate_views.py — regenerate this module's views/menus VIA erplibre_devops
# (the code generator), so they are never hand-authored.
#
# Usage (from the ERPLibre root, with the demo installed in a DB):
#   1. ./script/database/db_restore.py --database code_generator
#      ./script/addons/install_addons_dev.sh code_generator \
#          code_generator,erplibre_devops_sync_external_data,erplibre_construction_qc_demo
#   2. echo "exec(open('<this file>').read())" | \
#          ./odoo_bin.sh shell -c ./config.conf -d code_generator --no-http
#   3. Integrate /tmp/construction_qc_views_harvest/views/* into views/ :
#      copy the 4 construction_doc_*.xml, dedup menu.xml (1 root + 1 sub +
#      4 leaves, drop web_icon), update __manifest__.py.
#
# It drives code.generator.generate.views.wizard -> code.generator.writer
# against the 4 EXISTING models, whitelisting only the business fields, into
# a TEMP dir (never this module's path; the internal CG path does
# shutil.rmtree+copytree and would destroy the bespoke code). All DB mutations
# are rolled back; the emitted files survive on disk.
import os
import shutil

MODELS = [
    "construction.doc_soumission",
    "construction.doc_facture",
    "construction.doc_devis",
    "construction.doc_intervenant",
]
CG_NAME = "construction_qc"
KEEP_VIEW_TYPES = ["list", "form", "search"]
DEST = "/tmp/construction_qc_views_harvest"

print("=== STEP 0: confirm models installed ===")
for m in MODELS:
    rec = env["ir.model"].search([("model", "=", m)])
    if not rec:
        raise RuntimeError("Model %r not found — demo not installed?" % m)
    print("  OK", m, "id=", rec.id)

print(
    "=== STEP 1: unlink pre-existing views + act_windows (+ their xmlids) ==="
)
# Unlink (not blacklist) so regenerated list/form do not collide with the
# hand-written demo views' names/xmlids. All rolled back at the end.
pre_views = env["ir.ui.view"].search([("model", "in", MODELS)])
env["ir.model.data"].search(
    [("model", "=", "ir.ui.view"), ("res_id", "in", pre_views.ids)]
).unlink()
print("  unlinking", len(pre_views), "pre-existing views")
pre_views.unlink()
pre_actwin = env["ir.actions.act_window"].search([("res_model", "in", MODELS)])
env["ir.model.data"].search(
    [("model", "=", "ir.actions.act_window"), ("res_id", "in", pre_actwin.ids)]
).unlink()
print("  unlinking", len(pre_actwin), "pre-existing act_windows")
pre_actwin.unlink()

print("=== STEP 2: drop stale CG module + singleton ===")
old = env["code.generator.module"].search([("name", "=", CG_NAME)])
if old:
    for mm in old.o2m_models:
        mm.m2o_module = False
    old.unlink()
if hasattr(env.cr, "_code_generator_data"):
    del env.cr._code_generator_data

print("=== STEP 3: create code.generator.module ===")
cg = env["code.generator.module"].create(
    [
        {
            "name": CG_NAME,
            "shortdesc": "Construction QC Harvest (tmp)",
            "license": "AGPL-3",
            "author": "ERPLibre",
            "application": True,
            "enable_sync_code": False,
            "state": "uninstalled",
        }
    ]
)
print("  cg id=", cg.id)

print("=== STEP 4: attach existing models ===")
for m in MODELS:
    irm = env["ir.model"].search([("model", "=", m)])
    irm.m2o_module = cg.id
    print("  attached", m)
print("  o2m_models count=", len(cg.o2m_models))

print("=== STEP 4b: whitelist business fields (exclude mixin/technical) ===")
WHITELIST = {
    "construction.doc_soumission": [
        "numero_soumission",
        "nom_chantier",
        "code_projet",
        "entrepreneur_name",
        "montant",
        "date_soumission",
        "statut",
        "actif",
        "coordonnees_gps",
        "latitude",
        "longitude",
        "file_no_line",
        "project_id",
    ],
    "construction.doc_facture": [
        "no_facture",
        "numero_soumission",
        "date_echeance",
        "montant_paye",
        "fournisseur",
        "file_no_line",
        "project_id",
    ],
    "construction.doc_devis": [
        "numero_devis",
        "nom_chantier",
        "client_name",
        "client_email",
        "montant",
        "file_no_line",
        "partner_id",
        "crm_lead_id",
        "sale_order_id",
    ],
    "construction.doc_intervenant": [
        "nom",
        "courriel",
        "role",
        "type_label",
        "file_no_line",
        "partner_id",
    ],
}
for model_name, keep in WHITELIST.items():
    flds = env["ir.model.fields"].search(
        [("model", "=", model_name), ("name", "in", keep)]
    )
    if flds:
        # Direct SQL: ORM write is blocked on base (Python-defined) fields
        # by Odoo's base-field guard. Harvest-only, rolled back below.
        env.cr.execute(
            "UPDATE ir_model_fields SET "
            "is_show_whitelist_form_view = true, "
            "is_show_whitelist_list_view = true, "
            "is_show_whitelist_search_view = true "
            "WHERE id IN %s",
            (tuple(flds.ids),),
        )
    print("  whitelisted", len(flds), "/", len(keep), "on", model_name)
env.invalidate_all()

print("=== STEP 5: run view wizard ===")
wiz = env["code.generator.generate.views.wizard"].create(
    [
        {
            "code_generator_id": cg.id,
            "enable_generate_all": False,
            "all_model": True,
            "clear_all_menu": True,
            "clear_all_act_window": True,
            "clear_all_access": True,
            "clear_all_view": True,
            "disable_generate_access": False,
            "disable_generate_menu": False,
        }
    ]
)
wiz.button_generate_views()
print("  o2m_menus=", len(cg.o2m_menus))

print("=== STEP 5b: keep only list/form/search; fix act_window view_mode ===")
extra_views = env["ir.ui.view"].search(
    [("model", "in", MODELS), ("type", "not in", KEEP_VIEW_TYPES)]
)
extra_views.write({"is_hide_blacklist_write_view": True})
print("  suppressed", len(extra_views), "non-list/form/search views")
gen_actwin = env["ir.actions.act_window"].search([("res_model", "in", MODELS)])
gen_actwin.write({"view_mode": "list,form"})
print("  set view_mode=list,form on", len(gen_actwin), "act_windows")

print("=== STEP 6: create writer (emits files) ===")
writer = env["code.generator.writer"].create([{"code_generator_ids": cg.ids}])
print("  rootdir=", writer.rootdir)

print("=== STEP 7: list emitted files ===")
try:
    files = writer.get_list_path_file()
except Exception as e:  # noqa: BLE001
    print("  get_list_path_file failed:", e)
    files = []
for f in sorted(files):
    if f:
        print("   ", os.path.exists(f), f)

print("=== STEP 8: copy rootdir to", DEST, "===")
if writer.rootdir and os.path.isdir(writer.rootdir):
    if os.path.exists(DEST):
        shutil.rmtree(DEST)
    shutil.copytree(writer.rootdir, DEST)
    for root, _dirs, fnames in os.walk(DEST):
        for fn in fnames:
            print("   ", os.path.relpath(os.path.join(root, fn), DEST))
else:
    print("  !! rootdir missing — generation produced nothing")

print("=== STEP 9: rollback ===")
env.cr.rollback()
print("DONE. Harvest in", DEST)
