# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl)

from odoo.tests.common import TransactionCase


class TestDevopsPlanProject(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.system = cls.env["devops.system"].search([], limit=1)
        if not cls.system:
            cls.system = cls.env["devops.system"].create(
                {"method": "local"}
            )

    def _create_project(self, vals=None):
        defaults = {
            "society_name": "TestCo",
            "society_type": "projet",
            "project_type": "website_one_pager_alimentation",
        }
        if vals:
            defaults.update(vals)
        return self.env["devops.plan.project"].create(defaults)

    # ── Computed name ──

    def test_name_format(self):
        proj = self._create_project()
        self.assertIn("TestCo", proj.name)
        self.assertIn("projet", proj.name)

    def test_name_with_context(self):
        proj = self._create_project({"type_context": "bio"})
        self.assertIn("bio", proj.name)

    # ── has_aliment ──

    def test_has_aliment_alimentation(self):
        proj = self._create_project(
            {"project_type": "website_one_pager_alimentation"}
        )
        self.assertTrue(proj.has_aliment)

    def test_has_aliment_restaurant(self):
        proj = self._create_project(
            {
                "society_type": "restaurant",
                "project_type": "website_one_pager_magasin",
            }
        )
        self.assertTrue(proj.has_aliment)

    def test_no_aliment_magasin(self):
        proj = self._create_project(
            {
                "society_type": "projet",
                "project_type": "website_one_pager_magasin",
            }
        )
        self.assertFalse(proj.has_aliment)

    def test_no_aliment_sante(self):
        proj = self._create_project(
            {
                "society_type": "société",
                "project_type": "website_one_pager_sante",
            }
        )
        self.assertFalse(proj.has_aliment)

    # ── Defaults ──

    def test_default_temperature(self):
        proj = self._create_project()
        self.assertAlmostEqual(proj.temperature, 0.1)

    def test_default_step(self):
        proj = self._create_project()
        self.assertEqual(proj.step, 20)

    def test_default_gen_nb_aliment(self):
        proj = self._create_project()
        self.assertEqual(proj.gen_nb_aliment, 5)

    def test_default_website_max_one_pager(self):
        proj = self._create_project()
        self.assertEqual(proj.website_max_number_one_pager, 10)

    # ── All society types creatable ──

    def test_all_society_types(self):
        types = [
            "projet", "projet entrepreneurial", "société",
            "industrie", "magasin", "restaurant", "entreprise",
            "société à but non lucratif",
        ]
        for stype in types:
            proj = self._create_project(
                {
                    "society_name": f"Test_{stype}",
                    "society_type": stype,
                }
            )
            self.assertEqual(proj.society_type, stype)

    # ── All project types creatable ──

    def test_all_project_types(self):
        types = [
            "website_one_pager_alimentation",
            "website_one_pager_sante",
            "website_one_pager_magasin",
            "presentation_pptx_formation",
        ]
        for ptype in types:
            proj = self._create_project({"project_type": ptype})
            self.assertEqual(proj.project_type, ptype)

    # ── clear_result ──

    def test_clear_result(self):
        proj = self._create_project()
        proj.write(
            {
                "result_list_aliment_image": "some data",
                "question_list_aliment_image": "some question",
            }
        )
        proj.clear_result()
        self.assertFalse(proj.result_list_aliment_image)
