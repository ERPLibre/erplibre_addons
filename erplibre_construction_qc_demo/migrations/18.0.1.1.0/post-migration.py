# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)
import json
import logging

from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)

# data/sync_model.xml is noupdate="1", so the soumission metadata is NOT
# rewritten on a module upgrade. This migration force-adds the new
# « Coordonnées » -> coordonnees_gps header to existing installs so the
# geographic coordinate (Leaflet) is imported there too. Idempotent.
_HEADER_ENTRY = ["Coordonnées", "coordonnees_gps"]


@openupgrade.migrate()
def migrate(env, version):
    sync_model = env.ref(
        "erplibre_construction_qc_demo"
        ".sync_model_construction_doc_soumission",
        raise_if_not_found=False,
    )
    if not sync_model:
        return
    raw = sync_model.spreadsheet_extraction_metadata
    if not raw:
        return
    try:
        meta = json.loads(raw)
    except (ValueError, TypeError):
        _logger.warning(
            "sync_model_construction_doc_soumission: metadata JSON "
            "illisible, migration coordonnées ignorée."
        )
        return
    header = meta.get("header", [])
    if any(col and col[0] == _HEADER_ENTRY[0] for col in header):
        return
    header.append(_HEADER_ENTRY)
    meta["header"] = header
    sync_model.spreadsheet_extraction_metadata = json.dumps(
        meta, ensure_ascii=False, indent=4
    )
    _logger.info(
        "sync_model_construction_doc_soumission: header « Coordonnées » "
        "ajouté (migration géolocalisation)."
    )
