import logging

from odoo import SUPERUSER_ID, _, api, fields, models
from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    if openupgrade.column_exists(
        env.cr, "sync_data_transform", "modification"
    ):
        openupgrade.rename_fields(
            env,
            [
                (
                    "sync.data.transform.exec",
                    "sync_data_transform_exec",
                    "modification",
                    "modification_text",
                ),
            ],
        )
