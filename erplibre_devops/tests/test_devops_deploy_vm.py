# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsDeployVm(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.system = cls.env["devops.system"].search([], limit=1)
        if not cls.system:
            cls.system = cls.env["devops.system"].create(
                {"method": "local"}
            )

    def _create_vm(self, vals=None):
        defaults = {
            "name": "test-vm",
            "provider": "VirtualBox",
            "system_id": self.system.id,
        }
        if vals:
            defaults.update(vals)
        return self.env["devops.deploy.vm"].create(defaults)

    def test_create_virtualbox(self):
        vm = self._create_vm()
        self.assertEqual(vm.provider, "VirtualBox")

    def test_create_qemu(self):
        vm = self._create_vm({"provider": "Qemu"})
        self.assertEqual(vm.provider, "Qemu")

    def test_default_uri(self):
        vm = self._create_vm()
        self.assertEqual(vm.uri, "local")

    def test_no_exec_running_by_default(self):
        vm = self._create_vm()
        self.assertFalse(vm.has_vm_exec_running)

    def test_snapshot_relation(self):
        vm = self._create_vm()
        snapshot = self.env["devops.deploy.vm.snapshot"].create(
            {"name": "snap1", "vm_id": vm.id}
        )
        self.assertIn(snapshot, vm.vm_snapshot_ids)

    def test_workspace_association(self):
        workspace = self.env["devops.workspace"].search(
            [("is_me", "=", True)], limit=1
        )
        if not workspace:
            self.skipTest("No 'me' workspace")
        vm = self._create_vm()
        vm.write({"workspace_ids": [(4, workspace.id)]})
        self.assertIn(workspace, vm.workspace_ids)
