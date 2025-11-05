# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import os
import subprocess
import time

from odoo import SUPERUSER_ID, _, api

_logger = logging.getLogger(__name__)


def post_init_hook(cr, e):
    with api.Environment.manage():
        env = api.Environment(cr, SUPERUSER_ID, {})

        # Trick to attach a running process live
        # ok = False
        # first_print = False
        # while ok is False:
        #     time.sleep(1)
        #     if not first_print:
        #         first_print = True
        #         print(
        #             "Use PyCharm and do «Menu/Run/Attach to Process...»"
        #             " Ctrl+alt+5, and choose «./odoo/odoo-bin». I am waiting"
        #             " for ever! Add to watch «ok = True» + «Ctrl+Shift+Enter»."
        #         )

        # Generate system local
        if not os.environ.get("IS_ONLY_ME", False):
            # Search other ERPLibre accessible
            # TODO use instead workspace_me
            env.ref(
                "erplibre_devops.devops_system_local"
            ).action_search_workspace()
            # Search other System accessible
            # system_ids = env.ref(
            #     "erplibre_devops.devops_system_local"
            # ).get_local_system_ids(env)

            with env.ref(
                "erplibre_devops.devops_workspace_me"
            ).devops_create_exec_bundle("Search system SSH") as rec:
                system_ids = (
                    rec.system_id.get_local_system_id_from_ssh_config()
                )

                for system_id in system_ids:
                    system_id.action_search_workspace()
                    under_system_ids = (
                        system_id.get_local_system_id_from_ssh_config()
                    )
                    # under_system_ids = system_id.get_local_system_ids(env)
                    # Too much time, user will ask later
                    # if under_system_ids:
                    #     under_system_ids.action_search_workspace()
        # select Selenium
        arg_selenium = ""
        if os.environ.get("OPEN_DASHBOARD", False):
            arg_selenium = " --open_dashboard"

        if os.environ.get("IS_ME_AUTO", False):
            subprocess.Popen(
                f"cd {os.getcwd()};./.venv/bin/python"
                " ./script/selenium/web_login.py"
                f" --open_me_devops_auto{arg_selenium}",
                shell=True,
            )
        elif os.environ.get("IS_ME_AUTO_FORCE", False):
            subprocess.Popen(
                f"cd {os.getcwd()};./.venv/bin/python"
                " ./script/selenium/web_login.py"
                f" --open_me_devops_auto_force{arg_selenium}",
                shell=True,
            )
        elif arg_selenium:
            subprocess.Popen(
                f"cd {os.getcwd()};./.venv/bin/python"
                f" ./script/selenium/web_login.py{arg_selenium}",
                shell=True,
            )
        else:
            subprocess.Popen(
                f"cd {os.getcwd()};./.venv/bin/python"
                " ./script/selenium/web_login.py"
                f" --open_me_devops{arg_selenium}",
                shell=True,
            )


# def get_local_system_ids(env):
#     with env.ref(
#         "erplibre_devops.devops_workspace_me"
#     ).devops_create_exec_bundle("Search system SSH") as rec:
#         system_ids = rec.system_id.get_local_system_id_from_ssh_config(rec)
#         return system_ids
