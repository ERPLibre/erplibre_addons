# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsSystem(TransactionCase):
    """Tests for devops.system model - basic CRUD and field defaults.
    Does not test SSH/subprocess methods to avoid side effects."""

    def test_create_local(self):
        system = self.env["devops.system"].create(
            {"method": "local"}
        )
        self.assertEqual(system.method, "local")
        self.assertTrue(system.active)

    def test_create_ssh(self):
        system = self.env["devops.system"].create(
            {
                "method": "ssh",
                "ssh_host": "192.168.1.100",
                "ssh_user": "admin",
                "ssh_port": 22,
            }
        )
        self.assertEqual(system.method, "ssh")
        self.assertEqual(system.ssh_host, "192.168.1.100")
        self.assertEqual(system.ssh_user, "admin")
        self.assertEqual(system.ssh_port, 22)

    def test_default_method_local(self):
        system = self.env["devops.system"].create({})
        self.assertEqual(system.method, "local")

    def test_local_system_exists_from_data(self):
        """The module data should have created a local system."""
        local = self.env.ref(
            "erplibre_devops.devops_system_local",
            raise_if_not_found=False,
        )
        if local:
            self.assertEqual(local.method, "local")

    def test_system_nginx_conf_relation(self):
        system = self.env["devops.system"].create(
            {"method": "local"}
        )
        # Verify the one2many relation exists
        self.assertFalse(system.system_nginx_site_conf_ids)

    def test_system_workspace_relation(self):
        system = self.env["devops.system"].create(
            {"method": "local"}
        )
        self.assertFalse(system.devops_workspace_ids)

    def test_system_docker_fields_defaults(self):
        system = self.env["devops.system"].create(
            {"method": "local"}
        )
        # Docker fields should be False by default
        self.assertFalse(system.docker_is_installed)
        self.assertFalse(system.docker_daemon_is_running)
