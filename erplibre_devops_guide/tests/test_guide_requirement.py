# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from ..models.devops_guide_card import REQUIREMENT_KEYS


def _leaked_false(value):
    """Rend les valeurs `False` trouvées dans un arbre de dict et de list.

    Comparaison par identité : 0 == False, et un champ valant 0 ne doit
    pas faire échouer le test à tort.
    """
    if isinstance(value, dict):
        return [item for v in value.values() for item in _leaked_false(v)]
    if isinstance(value, list):
        return [item for v in value for item in _leaked_false(v)]
    return [value] if value is False else []


@tagged("post_install", "-at_install")
class TestGuideRequirement(TransactionCase):
    """Une carte rattachée à un requis rend son état, sa visite et ses droits.

    Chaque carte porte un `requirement` aux mêmes clés, rempli ou vide,
    jamais False ; la visite de la carte l'emporte sur celle du requis ;
    une carte réservée à des groupes, ou un bouton qui mène vers une cible
    que le lecteur ne peut pas ouvrir, ne lui est pas rendu.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        category = cls.env["devops.requirement.category"].create(
            {"code": "zz_test", "name": "Test domain"}
        )
        cls.requirement = cls.env["devops.requirement"].create(
            {
                "code": "ZZ-001",
                "name": "Export the inventory",
                "category_id": category.id,
                "moscow": "must",
            }
        )
        cls.env["devops.requirement.test"].create(
            {
                "requirement_id": cls.requirement.id,
                "kind": "tour",
                "reference": "zz_requirement_tour",
            }
        )
        # Ni code ni niveau : les deux se relisent False côté Python.
        cls.bare_requirement = cls.env["devops.requirement"].create(
            {
                "name": "Bare requirement",
                "category_id": category.id,
                "moscow": False,
            }
        )
        cls.guide = cls.env["devops.guide"].create(
            {"name": "Requirement page test", "title": "Inventory"}
        )
        cls.section = cls.env["devops.guide.section"].create(
            {"guide_id": cls.guide.id, "kind": "cards", "title": "S"}
        )
        cls.card_req = cls._card("Linked", requirement_id=cls.requirement.id)
        cls.card_bare = cls._card(
            "Bare", requirement_id=cls.bare_requirement.id
        )
        cls.card_plain = cls._card("Plain")
        cls.internal = new_test_user(
            cls.env, login="zz_guide_internal", groups="base.group_user"
        )
        cls.admin = new_test_user(
            cls.env,
            login="zz_guide_admin",
            groups="base.group_user,base.group_system",
        )

    @classmethod
    def _card(cls, title, **vals):
        return cls.env["devops.guide.card"].create(
            dict(section_id=cls.section.id, title=title, **vals)
        )

    def _page_cards(self, user=None, guide=None):
        # Les libellés de repli passent par `_()` : en anglais forcé, les
        # assertions tiennent aussi sur une base chargée en fr_CA.
        guide = (guide or self.guide).with_context(lang="en_US")
        if user:
            guide = guide.with_user(user)
        return {
            card["title"]: card
            for section in guide.get_page()["sections"]
            for card in section["cards"]
        }

    # -- Sans False ------------------------------------------------------

    def test_page_carries_no_false_with_and_without_requirement(self):
        page = self.guide.with_user(self.internal).get_page()
        self.assertFalse(_leaked_false(page), "get_page must not leak a False")

    def test_card_without_requirement_has_empty_keys(self):
        card = self._page_cards(self.internal)["Plain"]
        self.assertEqual(
            card["requirement"], dict.fromkeys(REQUIREMENT_KEYS, "")
        )

    def test_bare_requirement_renders_strings(self):
        requirement = self._page_cards(self.internal)["Bare"]["requirement"]
        self.assertEqual(requirement["code"], "")
        self.assertEqual(requirement["moscow"], "")
        self.assertEqual(requirement["moscow_label"], "")
        self.assertEqual(requirement["has_guide"], "")

    # -- Le requis de la carte -------------------------------------------

    def test_requirement_block_carries_state_and_labels(self):
        requirement = self._page_cards(self.internal)["Linked"]["requirement"]
        self.assertEqual(requirement["id"], self.requirement.id)
        self.assertEqual(requirement["code"], "ZZ-001")
        self.assertEqual(requirement["name"], "Export the inventory")
        self.assertEqual(requirement["moscow"], "must")
        self.assertEqual(requirement["moscow_label"], "Must have")
        # L'étape par défaut du requis : planifié, pas encore livré.
        self.assertEqual(requirement["stage"], "plan")
        self.assertEqual(requirement["stage_label"], "Plan")
        self.assertEqual(requirement["test_state"], "not_run")
        self.assertEqual(requirement["test_state_label"], "Not run")
        self.assertEqual(requirement["has_guide"], "")

    def test_requirement_block_has_every_key(self):
        requirement = self._page_cards(self.internal)["Linked"]["requirement"]
        self.assertEqual(set(requirement), set(REQUIREMENT_KEYS))
        self.assertIn("stage", REQUIREMENT_KEYS)
        self.assertIn("stage_label", REQUIREMENT_KEYS)

    def test_stage_follows_the_requirement(self):
        # Un requis en exploitation est livré : la page le dit par son
        # étape, que le niveau MoSCoW ne porte pas.
        self.requirement.devsecops_stage = "operate"
        requirement = self._page_cards(self.internal)["Linked"]["requirement"]
        self.assertEqual(requirement["stage"], "operate")
        self.assertEqual(requirement["stage_label"], "Operate")

    def test_has_guide_follows_the_guide_field(self):
        detail = self.env["devops.guide"].create(
            {"name": "Detail", "title": "Detail"}
        )
        self.requirement.guide_id = detail
        requirement = self._page_cards(self.internal)["Linked"]["requirement"]
        self.assertIs(requirement["has_guide"], True)
        self.assertEqual(self.requirement.guide_card_ids, self.card_req)

    # -- Visibilité par groupe -------------------------------------------

    def test_groups_hide_the_card_from_non_members(self):
        self.card_plain.groups_id = self.env.ref("base.group_system")
        self.assertNotIn("Plain", self._page_cards(self.internal))
        self.assertIn("Plain", self._page_cards(self.admin))

    def test_implied_group_counts_as_membership(self):
        # Un utilisateur interne inscrit au seul groupe qui implique celui
        # de la carte : il la voit par implication, sans passer par la
        # règle de l'administrateur.
        reader_group = self.env["res.groups"].create({"name": "zz_reader"})
        lead_group = self.env["res.groups"].create(
            {"name": "zz_lead", "implied_ids": [(4, reader_group.id)]}
        )
        lead = new_test_user(
            self.env, login="zz_guide_lead", groups="base.group_user"
        )
        lead.groups_id = [(4, lead_group.id)]
        self.card_plain.groups_id = reader_group
        self.assertIn("Plain", self._page_cards(lead))
        self.assertNotIn("Plain", self._page_cards(self.internal))

    def test_groups_hide_the_card_outside_the_page(self):
        # La restriction est une règle d'accès : l'onglet Guide du requis
        # et une recherche RPC ne rendent pas la carte non plus. Le cache
        # est vidé pour relire comme le ferait une nouvelle requête.
        self.card_req.groups_id = self.env.ref("base.group_system")
        self.env.invalidate_all()
        cards = self.env["devops.guide.card"].with_user(self.internal)
        self.assertFalse(cards.search([("id", "=", self.card_req.id)]))
        requirement = self.requirement.with_user(self.internal)
        self.assertFalse(requirement.guide_card_ids)
        self.env.invalidate_all()
        admin_requirement = self.requirement.with_user(self.admin)
        self.assertEqual(admin_requirement.guide_card_ids, self.card_req)

    def test_card_without_groups_is_visible_to_all(self):
        self.assertIn("Plain", self._page_cards(self.internal))

    # -- Visite effective ------------------------------------------------

    def test_effective_tour_falls_back_to_the_requirement(self):
        card = self._page_cards(self.internal)["Linked"]
        self.assertEqual(card["tour_name"], "zz_requirement_tour")

    def test_card_tour_wins_over_the_requirement(self):
        self.card_req.tour_name = "zz_card_tour"
        card = self._page_cards(self.internal)["Linked"]
        self.assertEqual(card["tour_name"], "zz_card_tour")

    def test_unreadable_requirement_blanks_the_card(self):
        # Une règle cache le requis à l'utilisateur interne : la carte reste
        # rendue, son bloc requis et sa visite empruntée vides, sans que la
        # page lève.
        self.env["ir.rule"].create(
            {
                "name": "zz hide one requirement",
                "model_id": self.env["ir.model"]._get_id("devops.requirement"),
                "groups": [(4, self.env.ref("base.group_user").id)],
                "domain_force": f"[('id', '!=', {self.requirement.id})]",
            }
        )
        card = self._page_cards(self.internal)["Linked"]
        self.assertEqual(
            card["requirement"], dict.fromkeys(REQUIREMENT_KEYS, "")
        )
        self.assertEqual(card["tour_name"], "")
        self.card_req.tour_name = "zz_card_tour"
        card = self._page_cards(self.internal)["Linked"]
        self.assertEqual(card["tour_name"], "zz_card_tour")

    def test_no_tour_renders_an_empty_string(self):
        self.assertEqual(
            self._page_cards(self.internal)["Plain"]["tour_name"], ""
        )

    def test_tour_label_falls_back_to_a_default(self):
        cards = self._page_cards(self.internal)
        self.assertEqual(cards["Plain"]["tour_label"], "Show me")
        self.card_plain.tour_label = "Watch it"
        self.assertEqual(
            self._page_cards(self.internal)["Plain"]["tour_label"], "Watch it"
        )

    def test_hero_tour_label_falls_back_to_a_default(self):
        page = self.guide.with_context(lang="en_US").get_page()
        self.assertEqual(page["tour_label"], "Start the tour")

    # -- Bouton d'action -------------------------------------------------

    def _action(self, xmlid_name, res_model, groups=None):
        action = self.env["ir.actions.act_window"].create(
            {
                "name": xmlid_name,
                "res_model": res_model,
                "groups_id": [(6, 0, groups.ids)] if groups else False,
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": "erplibre_devops_guide",
                "name": xmlid_name,
                "model": action._name,
                "res_id": action.id,
            }
        )
        return f"erplibre_devops_guide.{xmlid_name}"

    def _button(self, user, **vals):
        self.card_plain.write(dict(action_label="Open", **vals))
        card = self._page_cards(user)["Plain"]
        return card["action_xmlid"], card["action_label"]

    def test_reachable_action_keeps_its_button(self):
        xmlid = self._action("zz_action_open", "devops.guide")
        self.assertEqual(
            self._button(self.internal, action_xmlid=xmlid), (xmlid, "Open")
        )

    def test_unknown_action_removes_the_button(self):
        self.assertEqual(
            self._button(
                self.internal, action_xmlid="erplibre_devops_guide.zz_missing"
            ),
            ("", ""),
        )

    def test_xmlid_without_module_removes_the_button(self):
        # `env.ref` lève sur un identifiant sans point : la page s'ouvre.
        self.assertEqual(
            self._button(self.internal, action_xmlid="zz_no_module"), ("", "")
        )

    def test_xmlid_of_a_non_action_removes_the_button(self):
        self.assertEqual(
            self._button(self.internal, action_xmlid="base.group_user"),
            ("", ""),
        )

    def test_action_of_other_groups_removes_the_button(self):
        xmlid = self._action(
            "zz_action_admin",
            "devops.guide",
            self.env.ref("base.group_system"),
        )
        self.assertEqual(
            self._button(self.internal, action_xmlid=xmlid), ("", "")
        )
        self.assertEqual(
            self._button(self.admin, action_xmlid=xmlid), (xmlid, "Open")
        )

    def test_action_on_an_unreadable_model_removes_the_button(self):
        # L'utilisateur interne ne lit pas les paramètres système.
        xmlid = self._action("zz_action_params", "ir.config_parameter")
        self.assertEqual(
            self._button(self.internal, action_xmlid=xmlid), ("", "")
        )
        self.assertEqual(
            self._button(self.admin, action_xmlid=xmlid), (xmlid, "Open")
        )

    def test_unreadable_counted_model_removes_the_button(self):
        label = self._button(self.internal, count_model="ir.config_parameter")[
            1
        ]
        self.assertEqual(label, "")

    def test_removed_action_does_not_fall_back_to_the_counted_model(self):
        # L'action est inaccessible mais le modèle compté est lisible :
        # garder le libellé ferait ouvrir le modèle compté à la place de
        # l'action annoncée.
        self.assertEqual(
            self._button(
                self.internal,
                action_xmlid="erplibre_devops_guide.zz_missing",
                count_model="devops.guide",
            ),
            ("", ""),
        )

    # -- Guide détaillé du requis ----------------------------------------

    def test_action_open_guide_opens_the_page(self):
        detail = self.env["devops.guide"].create(
            {"name": "Detail", "title": "Detail page"}
        )
        self.requirement.guide_id = detail
        action = self.requirement.action_open_guide()
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "devops_guide.page")
        self.assertEqual(action["context"], {"guide_id": detail.id})

    def test_action_open_guide_without_guide_raises(self):
        with self.assertRaises(UserError):
            self.bare_requirement.action_open_guide()


@tagged("post_install", "-at_install")
class TestGuideRequirementFrCA(TransactionCase):
    """En fr_CA, les libellés que la page calcule arrivent traduits.

    Le repli des boutons de visite est une chaîne de code, lue dans
    i18n/fr_CA.po ; les libellés MoSCoW, d'étape et d'état de test sont
    ceux des sélections du module de requis, chargés en base avec la
    langue.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("fr_CA")
        cls.env["ir.module.module"]._load_module_terms(
            ["erplibre_devops_requirement", "erplibre_devops_guide"],
            ["fr_CA"],
            overwrite=True,
        )
        category = cls.env["devops.requirement.category"].create(
            {"code": "zz_test", "name": "Test domain"}
        )
        requirement = cls.env["devops.requirement"].create(
            {
                "code": "ZZ-FR",
                "name": "Export the inventory",
                "category_id": category.id,
                "moscow": "must",
            }
        )
        cls.guide = cls.env["devops.guide"].create(
            {"name": "French page test", "title": "Inventory"}
        )
        section = cls.env["devops.guide.section"].create(
            {"guide_id": cls.guide.id, "kind": "cards"}
        )
        cls.env["devops.guide.card"].create(
            {
                "section_id": section.id,
                "title": "Linked",
                "requirement_id": requirement.id,
            }
        )

    def test_labels_are_translated(self):
        page = self.guide.with_context(lang="fr_CA").get_page()
        card = page["sections"][0]["cards"][0]
        self.assertEqual(page["tour_label"], "Lancer la visite")
        self.assertEqual(card["tour_label"], "Me montrer")
        self.assertEqual(
            card["requirement"]["moscow_label"], "Doit (essentiel)"
        )
        self.assertEqual(card["requirement"]["stage_label"], "Planification")
        self.assertEqual(card["requirement"]["test_state_label"], "Aucun test")
