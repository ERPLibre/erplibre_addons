# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""La signature lue, enregistrée et effacée depuis le portail."""

import base64
import re

from odoo.tests import HttpCase, new_test_user, tagged

# PNG transparent de 1x1, en base64.
SIGNATURE_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhf"
    "DwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@tagged("post_install", "-at_install")
class TestErplibreUserSignaturePortal(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal_user = new_test_user(
            cls.env,
            login="signature_portal",
            password="signature_portal",
            groups="base.group_portal",
        )
        cls.other_user = new_test_user(
            cls.env,
            login="signature_portal_other",
            groups="base.group_portal",
        )
        cls.other_user.digital_signature = SIGNATURE_PNG

    def setUp(self):
        super().setUp()
        self.authenticate("signature_portal", "signature_portal")

    def _save(self, signature):
        return self.make_jsonrpc_request(
            "/my/signature", {"name": "Signataire", "signature": signature}
        )

    def test_save_own_signature(self):
        result = self._save(SIGNATURE_PNG)
        self.assertTrue(result["force_refresh"])
        self.assertEqual(result["redirect_url"], "/my/account")
        self.assertTrue(self.portal_user.digital_signature)
        self.assertTrue(self.other_user.digital_signature)

    def test_refuse_an_empty_or_unreadable_signature(self):
        svg = base64.b64encode(
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b"<script>alert(1)</script></svg>"
        ).decode()
        for signature in ("", "bm90IGFuIGltYWdl", svg):
            result = self._save(signature)
            self.assertTrue(result["error"], signature)
            self.assertFalse(self.portal_user.digital_signature, signature)

    def test_account_page_without_signature(self):
        page = self.url_open("/my/account").text
        self.assertIn("o_portal_user_signature", page)
        self.assertIn("portal.signature_form", page)
        self.assertNotIn("/my/signature/delete", page)

    def test_account_page_shows_and_deletes_signature(self):
        self._save(SIGNATURE_PNG)
        page = self.url_open("/my/account").text
        self.assertIn('src="data:image/png;base64,', page)
        section = page[page.index("o_portal_user_signature") :]
        token = re.search(r'name="csrf_token" value="([^"]+)"', section)
        response = self.url_open(
            "/my/signature/delete",
            data={"csrf_token": token.group(1)},
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        self.assertFalse(self.portal_user.digital_signature)
        self.assertTrue(self.other_user.digital_signature)

    def test_delete_requires_the_csrf_token(self):
        self._save(SIGNATURE_PNG)
        self.url_open("/my/signature/delete", data={"csrf_token": "x"})
        self.assertTrue(self.portal_user.digital_signature)

    def test_sign_from_the_account_page(self):
        """Le parcours du navigateur : ouvrir la fenêtre, signer en mode
        automatique, enregistrer, retrouver l'image sur la page."""
        self.start_tour(
            "/my/account",
            "erplibre_user_signature_portal",
            login="signature_portal",
        )
        self.assertTrue(self.portal_user.digital_signature)

    def test_account_page_in_fr_ca(self):
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            ["erplibre_user_signature_portal"], ["fr_CA"], overwrite=True
        )
        self.opener.cookies.set("frontend_lang", "fr_CA")
        page = self.url_open("/my/account").text
        self.assertIn("Ma signature", page)
        self.assertIn("Vous n'avez pas encore de signature.", page)
