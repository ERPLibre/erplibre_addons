import logging
from collections import defaultdict
from openupgradelib import openupgrade
from odoo import SUPERUSER_ID, _, api, fields, models

_logger = logging.getLogger(__name__)


@openupgrade.migrate()
def migrate(env, version):
    # Update variable
    sync_data_exec_ids = env["sync.data.exec"].search_fetch(
        [
            "|",
            ("sync_data_create_ids", "!=", False),
            ("mail_tracking_value_ids", "!=", False),
        ],
        ["mail_tracking_value_ids", "sync_data_create_ids"],
    )
    sync_data_exec_ids.update_modification_value()
