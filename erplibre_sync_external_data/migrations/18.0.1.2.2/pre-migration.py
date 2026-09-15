import logging

from odoo import SUPERUSER_ID, _, api, fields, models
from openupgradelib import openupgrade

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    openupgrade.rename_xmlids(
        env.cr,
        [
            (
                "erplibre_sync_external_data.group__erplibre_sync_external_data_exec_notify",
                "erplibre_sync_external_data.group_erplibre_sync_external_data_exec_notify",
            ),
        ],
    )
