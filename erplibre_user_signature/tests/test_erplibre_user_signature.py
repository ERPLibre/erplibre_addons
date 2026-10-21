# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Qui lit et écrit la signature d'un utilisateur, et où elle s'affiche."""

import base64

from lxml import etree
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tests.common import HttpCase, TransactionCase

# PNG transparent de 1x1, en base64.
SIGNATURE_PNG = (
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhf"
    b"DwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@tagged("post_install", "-at_install")
class TestErplibreUserSignature(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = new_test_user(
            cls.env, login="signature_owner", groups="base.group_user"
        )
        cls.colleague = new_test_user(
            cls.env, login="signature_colleague", groups="base.group_user"
        )
        cls.owner.digital_signature = SIGNATURE_PNG
        cls.colleague.digital_signature = SIGNATURE_PNG

    def test_owner_reads_and_writes_own_signature(self):
        own = self.owner.with_user(self.owner)
        self.assertEqual(
            own.read(["digital_signature"])[0]["digital_signature"],
            SIGNATURE_PNG,
        )
        own.write({"digital_signature": False})
        self.assertFalse(self.owner.digital_signature)

    def test_owner_clears_own_signature_with_the_button(self):
        self.owner.with_user(self.owner).clear_digital_signature()
        self.assertFalse(self.owner.digital_signature)

    def test_colleague_cannot_read_a_signature(self):
        with self.assertRaises(AccessError):
            self.colleague.with_user(self.owner).read(["digital_signature"])

    def test_access_rights_manager_cannot_change_a_signature(self):
        manager = new_test_user(
            self.env,
            login="signature_manager_write",
            groups="base.group_user,base.group_erp_manager",
        )
        colleague = self.colleague.with_user(manager)
        with self.assertRaises(AccessError):
            colleague.write({"digital_signature": False})
        with self.assertRaises(AccessError):
            colleague.clear_digital_signature()
        self.assertTrue(self.colleague.digital_signature)

    def test_colleague_cannot_search_on_signatures(self):
        users = self.env["res.users"].with_user(self.owner)
        with self.assertRaises(AccessError):
            users.search([("digital_signature", "!=", False)])
        admin = self.env.ref("base.user_admin")
        self.assertIn(
            self.colleague,
            users.with_user(admin).search(
                [("digital_signature", "!=", False)]
            ),
        )

    def test_owner_cannot_store_an_svg(self):
        svg = base64.b64encode(
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b"<script>alert(1)</script></svg>"
        )
        with self.assertRaises(ValidationError):
            self.owner.with_user(self.owner).write({"digital_signature": svg})
        self.assertEqual(self.owner.digital_signature, SIGNATURE_PNG)

    def test_admin_reads_any_signature(self):
        admin = self.env.ref("base.user_admin")
        self.assertTrue(
            self.colleague.with_user(admin).read(["digital_signature"])[0][
                "digital_signature"
            ]
        )

    def test_signature_in_preferences_view(self):
        """Un simple utilisateur voit et modifie le champ dans « Mon
        profil », libellé compris, bien qu'il soit réservé aux
        administrateurs ailleurs."""
        users = self.env["res.users"].with_user(self.owner)
        view = self.env.ref("base.view_users_form_simple_modif")
        arch = users.get_view(view.id, "form")["arch"]
        self.assertIn('name="digital_signature"', arch)
        self.assertIn('for="digital_signature"', arch)
        self.assertIn('name="clear_digital_signature"', arch)
        fields = users.fields_get(["digital_signature"])
        self.assertFalse(fields["digital_signature"]["readonly"])

    def test_clear_button_hidden_from_access_rights_managers(self):
        """Un gestionnaire des droits d'accès sans droits d'administrateur
        n'a pas de bouton d'effacement pour un champ qu'il ne peut écrire."""
        manager = new_test_user(
            self.env,
            login="signature_manager",
            groups="base.group_user,base.group_erp_manager",
        )
        view = self.env.ref("base.view_users_form")
        arch = (
            self.env["res.users"]
            .with_user(manager)
            .get_view(view.id, "form")["arch"]
        )
        self.assertNotIn('name="digital_signature"', arch)
        self.assertNotIn('name="clear_digital_signature"', arch)
        admin_arch = self.env["res.users"].get_view(view.id, "form")["arch"]
        self.assertIn('name="clear_digital_signature"', admin_arch)

    def test_auto_mode_is_offered_with_the_user_name(self):
        """Le widget n'affiche « Auto » que s'il connaît un nom : l'option
        « full_name » le prend dans « name », présent dans la vue."""
        for view_ref, user in (
            ("base.view_users_form_simple_modif", self.owner),
            ("base.view_users_form", self.env.ref("base.user_admin")),
        ):
            arch = etree.fromstring(
                self.env["res.users"]
                .with_user(user)
                .get_view(self.env.ref(view_ref).id, "form")["arch"]
            )
            field = arch.xpath("//field[@name='digital_signature']")
            self.assertTrue(field, view_ref)
            self.assertIn("'full_name': 'name'", field[0].get("options"))
            self.assertTrue(arch.xpath("//field[@name='name']"), view_ref)


@tagged("post_install", "-at_install")
class TestErplibreUserSignatureTour(HttpCase):
    def test_auto_mode_in_my_preferences(self):
        new_test_user(
            self.env, login="signature_tour", groups="base.group_user"
        )
        self.start_tour(
            "/odoo",
            "erplibre_user_signature_auto",
            login="signature_tour",
        )
