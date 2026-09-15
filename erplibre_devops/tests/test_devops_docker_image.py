# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsDockerImage(TransactionCase):
    def _create_image(self, vals=None):
        defaults = {
            "repository": "odoo",
            "tag": "18.0",
        }
        if vals:
            defaults.update(vals)
        return self.env["devops.docker.image"].create(defaults)

    def test_name_computed(self):
        image = self._create_image()
        self.assertEqual(image.name, "odoo:18.0")

    def test_name_with_different_repo_tag(self):
        image = self._create_image(
            {"repository": "postgres", "tag": "16"}
        )
        self.assertEqual(image.name, "postgres:16")

    def test_name_updates_on_tag_change(self):
        image = self._create_image()
        image.write({"tag": "17.0"})
        self.assertEqual(image.name, "odoo:17.0")

    def test_name_updates_on_repo_change(self):
        image = self._create_image()
        image.write({"repository": "erplibre"})
        self.assertEqual(image.name, "erplibre:18.0")

    def test_default_active(self):
        image = self._create_image()
        self.assertTrue(image.active)

    def test_name_with_empty_values(self):
        image = self._create_image(
            {"repository": False, "tag": False}
        )
        self.assertEqual(image.name, "False:False")
