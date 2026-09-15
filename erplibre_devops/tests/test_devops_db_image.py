# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsDbImage(TransactionCase):
    def test_create(self):
        image = self.env["devops.db.image"].create(
            {"name": "test_backup", "path": "/backups/test.zip"}
        )
        self.assertEqual(image.name, "test_backup")
        self.assertEqual(image.path, "/backups/test.zip")

    def test_create_multiple(self):
        images = self.env["devops.db.image"].create(
            [
                {"name": "backup_1", "path": "/backups/1.zip"},
                {"name": "backup_2", "path": "/backups/2.zip"},
            ]
        )
        self.assertEqual(len(images), 2)

    def test_search(self):
        self.env["devops.db.image"].create(
            {"name": "unique_name_123", "path": "/tmp/test.zip"}
        )
        found = self.env["devops.db.image"].search(
            [("name", "=", "unique_name_123")]
        )
        self.assertEqual(len(found), 1)
