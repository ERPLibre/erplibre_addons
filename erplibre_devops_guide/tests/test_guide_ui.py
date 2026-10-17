# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import HttpCase, tagged

# Visite déclarée par `web` dans `web.assets_tests`, chargé quand le
# serveur tourne en mode test : elle est au registre JS pendant ce test.
REGISTERED_TOUR = "test_user_switch"

# Contrôles faits dans la page une fois la première carte rendue. Tout
# `console.error` fait échouer le test ; `test successful` le réussit.
CHECK_PAGE = """
const fail = (message) => console.error("Guide page check failed: " + message);
const grid = document.querySelector(".o_devops_guide_grid");
const linked = grid.querySelector(".o_devops_guide_card");
const code = linked.querySelector(".o_devops_guide_pill_code");
const roadmapStep = document.querySelector(".o_devops_guide_step");
// Les boutons se reconnaissent à leur icône, pas à leur libellé : la
// base peut être chargée en fr_CA, qui traduit « Requirement ».
const linkIcons = [...linked.querySelectorAll(".o_devops_guide_card_link i")]
    .map((icon) => (icon.className.match(/fa-(list-alt|book)/) || [""])[0]);
if (!code || code.textContent.trim() !== "ZZ-UI") {
    fail("requirement code pill missing");
} else if (!linked.querySelector(".o_devops_guide_pill_test_not_run")) {
    fail("test state pill missing");
} else if (linked.querySelector(".o_devops_guide_card_tour")) {
    fail("a tour button is shown for an unregistered tour");
} else if (linkIcons.join("|") !== "fa-list-alt|fa-book") {
    fail("requirement and guide buttons expected, got " + linkIcons.join("|"));
} else if (!roadmapStep.querySelector(".o_devops_guide_pill_req")) {
    fail("roadmap step renders no pill");
} else if (!roadmapStep.querySelector(".o_devops_guide_card_tour")) {
    fail("roadmap step renders no button for a registered tour");
} else if (document.querySelector(".o_devops_guide_hero .o_devops_guide_btn_primary")) {
    fail("a hero tour button is shown for an unregistered tour");
} else {
    console.log("test successful");
}
"""


@tagged("post_install", "-at_install")
class TestGuideUi(HttpCase):
    """La page rend pastilles et boutons de requis, sans bouton muet.

    Le composant OWL est rendu dans Chrome headless : une carte de grille
    et une étape de feuille de route rattachées à un requis portent sa
    pastille et ses boutons, et un bouton de visite n'apparaît que pour
    une visite connue du registre JS.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Sans démo, l'Onboarding de l'administrateur est actif : une
        # visite native démarrerait au chargement, par-dessus la page.
        cls.env.ref("base.user_admin").tour_enabled = False
        category = cls.env["devops.requirement.category"].create(
            {"code": "zz_test", "name": "Test domain"}
        )
        detail = cls.env["devops.guide"].create(
            {"name": "Detail", "title": "Detail page"}
        )
        requirement = cls.env["devops.requirement"].create(
            {
                "code": "ZZ-UI",
                "name": "Export the inventory",
                "category_id": category.id,
                "moscow": "must",
                "guide_id": detail.id,
            }
        )
        cls.env["devops.requirement.test"].create(
            {
                "requirement_id": requirement.id,
                "kind": "tour",
                "reference": "zz_unregistered_tour",
            }
        )
        guide = cls.env["devops.guide"].create(
            {
                "name": "Ui test",
                "title": "Inventory",
                "tour_name": "zz_unregistered_tour",
            }
        )
        section = cls.env["devops.guide.section"]
        grid = section.create(
            {"guide_id": guide.id, "kind": "cards", "sequence": 1}
        )
        roadmap = section.create(
            {"guide_id": guide.id, "kind": "roadmap", "sequence": 2}
        )
        card = cls.env["devops.guide.card"]
        card.create(
            {
                "section_id": grid.id,
                "title": "Linked",
                "requirement_id": requirement.id,
            }
        )
        card.create(
            {
                "section_id": roadmap.id,
                "num": "1",
                "title": "Step",
                "requirement_id": requirement.id,
                "tour_name": REGISTERED_TOUR,
            }
        )
        cls.action = cls.env["ir.actions.client"].create(
            {
                "name": "Ui test",
                "tag": "devops_guide.page",
                "context": f"{{'guide_id': {guide.id}}}",
            }
        )

    def test_guide_page_renders_requirement_cards(self):
        self.browser_js(
            f"/odoo/action-{self.action.id}",
            CHECK_PAGE,
            ready="!!document.querySelector('.o_devops_guide_card')",
            login="admin",
        )
