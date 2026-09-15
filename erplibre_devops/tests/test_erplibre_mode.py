# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestErplibreMode(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mode_env = cls.env["erplibre.mode.env"].create(
            {"name": "dev", "value": "dev"}
        )
        cls.mode_exec = cls.env["erplibre.mode.exec"].create(
            {"name": "docker", "value": "docker"}
        )
        cls.mode_source = cls.env["erplibre.mode.source"].create(
            {"name": "git", "value": "git"}
        )

    def _create_mode(self):
        version_base = self.env["erplibre.mode.version.base"].create(
            {"name": "18.0", "value": "18.0"}
        )
        version_erplibre = self.env[
            "erplibre.mode.version.erplibre"
        ].create({"name": "1.6.0", "value": "1.6.0"})
        return self.env["erplibre.mode"].create(
            {
                "mode_env": self.mode_env.id,
                "mode_exec": self.mode_exec.id,
                "mode_source": self.mode_source.id,
                "mode_version_base": version_base.id,
                "mode_version_erplibre": version_erplibre.id,
            }
        )

    # ── Computed name ──

    def test_name_format(self):
        mode = self._create_mode()
        self.assertIn("dev", mode.name)
        self.assertIn("docker", mode.name)
        self.assertIn("git", mode.name)
        self.assertIn("18.0", mode.name)
        self.assertIn("1.6.0", mode.name)
        self.assertTrue(mode.name.startswith("{"))
        self.assertTrue(mode.name.endswith("}"))

    # ── get_mode() ──

    def test_get_mode_creates_new(self):
        mode = self.env["erplibre.mode"].get_mode(
            self.mode_env,
            self.mode_exec,
            self.mode_source,
            "17.0",
            "1.5.0",
        )
        self.assertTrue(mode)
        self.assertIn("17.0", mode.name)
        self.assertIn("1.5.0", mode.name)

    def test_get_mode_returns_existing(self):
        mode1 = self.env["erplibre.mode"].get_mode(
            self.mode_env,
            self.mode_exec,
            self.mode_source,
            "16.0",
            "1.4.0",
        )
        mode2 = self.env["erplibre.mode"].get_mode(
            self.mode_env,
            self.mode_exec,
            self.mode_source,
            "16.0",
            "1.4.0",
        )
        self.assertEqual(mode1.id, mode2.id)

    def test_get_mode_creates_missing_versions(self):
        """get_mode should create version records if they don't exist."""
        mode = self.env["erplibre.mode"].get_mode(
            self.mode_env,
            self.mode_exec,
            self.mode_source,
            "99.0",
            "99.0.0",
        )
        self.assertTrue(mode)
        version_base = self.env["erplibre.mode.version.base"].search(
            [("value", "=", "99.0")]
        )
        self.assertTrue(version_base)
        version_erplibre = self.env[
            "erplibre.mode.version.erplibre"
        ].search([("value", "=", "99.0.0")])
        self.assertTrue(version_erplibre)

    # ── Sub-models ──

    def test_mode_env_create(self):
        env = self.env["erplibre.mode.env"].create(
            {"name": "test_env", "value": "test"}
        )
        self.assertEqual(env.name, "test_env")

    def test_mode_exec_default_active(self):
        exec_mode = self.env["erplibre.mode.exec"].create(
            {"name": "active_mode", "value": "val"}
        )
        self.assertTrue(exec_mode.active)

    def test_mode_version_base_is_tag(self):
        version = self.env["erplibre.mode.version.base"].create(
            {"name": "v18.0", "value": "18.0", "is_tag": True}
        )
        self.assertTrue(version.is_tag)

    def test_mode_version_erplibre_is_tag(self):
        version = self.env["erplibre.mode.version.erplibre"].create(
            {"name": "v1.6.0", "value": "1.6.0", "is_tag": True}
        )
        self.assertTrue(version.is_tag)

    def test_mode_source_create(self):
        source = self.env["erplibre.mode.source"].create(
            {"name": "local", "value": "local"}
        )
        self.assertEqual(source.value, "local")
