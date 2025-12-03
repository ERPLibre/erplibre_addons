#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

from odoo import SUPERUSER_ID, _, api

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    # Refresh DB image
    env["devops.system"].action_refresh_db_image()

    # Force inbox for admin user
    env.ref("base.user_admin").write({"notification_type": "inbox"})

    # Create is me from this instance
    env.ref(
        "erplibre_devops.devops_workspace_me"
    ).action_install_me_workspace()

    # Update configuration
    settings = env["res.config.settings"].sudo()
    settings.auto_select_terminal()
    settings.auto_select_use_search_cmd()
