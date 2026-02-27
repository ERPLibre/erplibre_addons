import logging

from odoo import SUPERUSER_ID, _, api, fields, models
from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    if openupgrade.column_exists(
        env.cr, "sync_data_transform_exec", "res_model"
    ):
        openupgrade.rename_fields(
            env,
            [
                (
                    "sync.data.transform.exec",
                    "sync_data_transform_exec",
                    "res_model",
                    "to_model_name",
                ),
            ],
        )
        openupgrade.rename_fields(
            env,
            [
                (
                    "sync.data.transform.exec",
                    "sync_data_transform_exec",
                    "res_id",
                    "to_id_ref",
                ),
            ],
        )
        openupgrade.rename_fields(
            env,
            [
                (
                    "sync.data.transform.exec",
                    "sync_data_transform_exec",
                    "source_mirror_id_i",
                    "from_id_ref",
                ),
            ],
        )
        openupgrade.rename_fields(
            env,
            [
                (
                    "sync.data.transform.exec",
                    "sync_data_transform_exec",
                    "source_mirror_model_name",
                    "from_model_name",
                ),
            ],
        )
