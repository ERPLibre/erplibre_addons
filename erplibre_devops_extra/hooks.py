# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, _, api

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    action = env.ref("board.open_board_my_dash_action")
    menu_board = env.ref("board.menu_board_my_dash")
    action_workspace_view = env.ref(
        "erplibre_devops.action_devops_check_workspace_conf_form"
    )
    action_system_view = env.ref(
        "erplibre_devops.action_devops_check_system_conf_form"
    )
    action_vm_view = env.ref(
        "erplibre_devops.devops_deploy_vm_deploy_vm_action_window"
    )
    arch = f"""
<form string="Mon tableau de bord">
    <board style="2-1">
        <column>
            <action name="{action_workspace_view.id}" string="Workspace ME" view_mode="list" context="{{'lang': 'fr_CA', 'tz': 'America/Montreal', 'uid': 2, 'group_by': [], 'orderedBy': [], 'dashboard_merge_domains_contexts': False}}" domain="[['is_me', '=', True]]" modifiers="{{}}"></action>
            <action name="{action_workspace_view.id}" string="Working workspace" view_mode="list" context="{{'lang': 'fr_CA', 'tz': 'America/Montreal', 'uid': 2, 'group_by': ['system_id'], 'orderedBy': [], 'dashboard_merge_domains_contexts': False}}" domain="[['is_me', '!=', True]]" modifiers="{{}}"></action>
            <action name="{action_vm_view.id}" string="Deploy vm" view_mode="list" context="{{'lang': 'fr_CA', 'tz': 'America/Montreal', 'uid': 2, 'group_by': ['system_id'], 'orderedBy': [], 'dashboard_merge_domains_contexts': False}}" domain="[]"></action>
        </column><column>
            <action name="{action_system_view.id}" string="System" view_mode="kanban" context="{{'lang': 'fr_CA', 'tz': 'America/Montreal', 'uid': 2, 'params': {{'action': {action_system_view.id}, 'model': 'devops.system', 'view_type': 'list', 'menu_id': {menu_board.id}}}, 'group_by': [], 'dashboard_merge_domains_contexts': False}}" domain="" modifiers="{{}}"></action>
        </column><column>
        </column>
    </board>
</form>
    """
    env["ir.ui.view.custom"].create(
        [
            {
                "user_id": env.ref("base.user_admin").id,
                "ref_id": env.ref("board.board_my_dash_view").id,
                "arch": arch,
            }
        ]
    )
