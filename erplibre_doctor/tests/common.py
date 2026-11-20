# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
import os
import shutil
import tempfile

from odoo import release
from odoo.addons.erplibre_info import runner
from odoo.tests import TransactionCase

from .. import suggestion

# Invented module names: the module list of the test database holds none
# of them until a test creates it.
MODULE_UNINSTALLED = "erplibre_doctor_test_uninstalled"
MODULE_ABSENT = "erplibre_doctor_test_absent"


class DoctorCase(TransactionCase):
    """A fake ERPLibre checkout whose base image of this series suggests
    ``base`` (installed), an uninstalled module and a module the database
    does not know; the ``erplibre_info.root`` parameter names it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = tempfile.mkdtemp(prefix="erplibre_doctor_test_")
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        cls.image = suggestion.image_name(release.series)
        cls.config = {
            cls.image: {
                "base": "",
                "image_list": [
                    {"module": ["base", MODULE_UNINSTALLED, MODULE_ABSENT]}
                ],
            }
        }
        cls.write_config(cls.config)
        cls.env["ir.config_parameter"].sudo().set_param(
            runner.PARAM_ROOT, cls.root
        )
        cls.uninstalled = cls.env["ir.module.module"].create(
            {"name": MODULE_UNINSTALLED, "state": "uninstalled"}
        )
        cls.Report = cls.env["erplibre.doctor.report"]

    @classmethod
    def write_config(cls, data):
        path = os.path.join(cls.root, suggestion.CONFIG_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            if isinstance(data, str):
                fh.write(data)
            else:
                json.dump(data, fh)

    def new_report(self):
        action = self.Report.action_new_analysis()
        return self.Report.browse(action["res_id"])
