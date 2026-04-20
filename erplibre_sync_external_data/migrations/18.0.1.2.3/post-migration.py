import logging

from odoo import SUPERUSER_ID, _, api, fields, models
from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    if openupgrade.column_exists(
        env.cr, "sync_data_transform", "filter_search"
    ):
        openupgrade.rename_fields(
            env,
            [
                (
                    "sync.data.transform",
                    "sync_data_transform",
                    "filter_search",
                    "filter_search_legacy",
                ),
            ],
        )
    # Recompute all transform exec name
    env["sync.data.transform.exec"].search([])._compute_name()
