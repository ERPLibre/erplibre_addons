# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""La signature du profil offerte, adoptée et enregistrée depuis une case de
signature de sign_oca."""

import base64
import io
import json
from unittest.mock import patch

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import misc
from PIL import Image


def _image_base64(color, output_format="PNG", size=(4, 2)):
    """Rend une image unie de ``size`` en base64 ; chaque couleur donne une
    signature distincte des autres."""
    mode = "RGBA" if output_format == "PNG" else "RGB"
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, output_format)
    return base64.b64encode(buffer.getvalue())


SIGNER_PNG = _image_base64((0, 0, 128, 255))
OTHER_PNG = _image_base64((128, 0, 0, 255))
SIGNER_JPEG = _image_base64((0, 128, 0), "JPEG")

# Le code exécuté dans la page de signature : il attend que la visionneuse
# PDF ait posé la case de signature, puis ouvre la fenêtre de signature.
# ``%(steps)s`` reçoit la suite du parcours ; la réussite s'annonce par
# « test successful », un échec par une erreur dans la console.
BROWSER_CODE = """
(async () => {
    const waitFor = async (check, label) => {
        for (let i = 0; i < 300; i++) {
            const found = check();
            if (found) {
                return found;
            }
            await new Promise((resolve) => setTimeout(resolve, 100));
        }
        throw new Error("Timeout: " + label);
    };
    const frame = () =>
        document.querySelector("iframe.o_sign_oca_iframe")?.contentDocument;
    const field = () =>
        frame()?.querySelector(".o_sign_oca_field[data-field='%(item)s']");
    try {
        const box = await waitFor(() => field()?.firstElementChild, "field");
        box.click();
        await waitFor(() => document.querySelector(".modal"), "dialog");
        %(steps)s
    } catch (error) {
        console.error(String(error));
    }
})()
"""


@tagged("post_install", "-at_install")
class TestErplibreUserSignatureSignOca(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.signer_user = new_test_user(
            cls.env,
            login="sign_oca_profile_signer",
            password="sign_oca_profile_signer",
            groups="base.group_portal",
        )
        cls.other_user = new_test_user(
            cls.env,
            login="sign_oca_profile_other",
            password="sign_oca_profile_other",
            groups="base.group_user",
        )
        cls.signer_user.digital_signature = SIGNER_PNG
        cls.other_user.digital_signature = OTHER_PNG
        with open(misc.file_path("sign_oca/tests/empty.pdf"), "rb") as pdf:
            data = base64.b64encode(pdf.read())
        role = cls.env.ref("sign_oca.sign_role_customer")
        cls.sign_request = cls.env["sign.oca.request"].create(
            {
                "data": data,
                "name": "Profile signature test",
                "signer_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": cls.signer_user.partner_id.id,
                            "role_id": role.id,
                        },
                    )
                ],
            }
        )
        cls.item = cls.sign_request.add_item(
            {
                "field_id": cls.env.ref("sign_oca.sign_field_signature").id,
                "role_id": role.id,
                "page": 1,
                "position_x": 10,
                "position_y": 10,
                "width": 30,
                "height": 10,
                "required": True,
            }
        )
        cls.sign_request.action_send()
        cls.signer = cls.sign_request.signer_ids
        cls.info_url = (
            f"/sign_oca/info/{cls.signer.id}/{cls.signer.access_token}"
        )

    def _info_as(self, user):
        """Les données de la page lues hors requête HTTP : l'utilisateur de
        l'environnement est alors celui de la session."""
        return self.signer.with_user(user).sudo().get_info()

    def _png_uri(self, signature):
        return "data:image/png;base64," + signature.decode()

    # get_info

    def test_signer_is_offered_own_signature(self):
        info = self._info_as(self.signer_user)
        self.assertEqual(
            info["user_signature"], {"image": self._png_uri(SIGNER_PNG)}
        )

    def test_another_user_is_offered_nothing(self):
        """Ni la signature du signataire ni la sienne : l'utilisateur
        connecté n'est pas le signataire."""
        info = self._info_as(self.other_user)
        self.assertFalse(info["user_signature"])
        dumped = json.dumps(info)
        self.assertNotIn(SIGNER_PNG.decode(), dumped)
        self.assertNotIn(OTHER_PNG.decode(), dumped)

    def test_signer_check_is_a_hook(self):
        """``_is_user_signature_signer`` décide qui signe pour le
        signataire : un module qui y accepte un autre utilisateur lui offre
        sa propre signature."""
        signer_class = type(self.env["sign.oca.request.signer"])
        with patch.object(
            signer_class,
            "_is_user_signature_signer",
            lambda signer, user: user == self.other_user,
        ):
            info = self._info_as(self.other_user)
        self.assertEqual(
            info["user_signature"], {"image": self._png_uri(OTHER_PNG)}
        )
        self.assertNotIn(SIGNER_PNG.decode(), json.dumps(info))

    def test_admin_is_offered_nothing(self):
        info = self._info_as(self.env.ref("base.user_admin"))
        self.assertFalse(info["user_signature"])
        self.assertNotIn(SIGNER_PNG.decode(), json.dumps(info))

    def test_public_user_is_offered_nothing(self):
        info = self._info_as(self.env.ref("base.public_user"))
        self.assertFalse(info["user_signature"])

    def test_signer_without_signature(self):
        self.signer_user.digital_signature = False
        info = self._info_as(self.signer_user)
        self.assertEqual(info["user_signature"], {"image": False})

    def test_jpeg_signature_is_offered_as_png(self):
        """La case de sign_oca ne garde qu'un URI PNG : un JPEG du profil y
        arrive converti."""
        self.signer_user.digital_signature = SIGNER_JPEG
        image = self._info_as(self.signer_user)["user_signature"]["image"]
        prefix = "data:image/png;base64,"
        self.assertTrue(image.startswith(prefix))
        decoded = Image.open(
            io.BytesIO(base64.b64decode(image.removeprefix(prefix)))
        )
        self.assertEqual(decoded.format, "PNG")

    # /sign_oca/info, la route du portail

    def test_info_route_anonymous(self):
        info = self.make_jsonrpc_request(self.info_url)
        self.assertFalse(info["user_signature"])
        self.assertNotIn(SIGNER_PNG.decode(), json.dumps(info))

    def test_info_route_logged_in_signer(self):
        self.authenticate("sign_oca_profile_signer", "sign_oca_profile_signer")
        info = self.make_jsonrpc_request(self.info_url)
        self.assertEqual(
            info["user_signature"], {"image": self._png_uri(SIGNER_PNG)}
        )

    def test_info_route_logged_in_other_user(self):
        self.authenticate("sign_oca_profile_other", "sign_oca_profile_other")
        info = self.make_jsonrpc_request(self.info_url)
        self.assertFalse(info["user_signature"])
        dumped = json.dumps(info)
        self.assertNotIn(SIGNER_PNG.decode(), dumped)
        self.assertNotIn(OTHER_PNG.decode(), dumped)

    # /sign_oca/user_signature/save

    def _save(self, signature, **params):
        return self.make_jsonrpc_request(
            "/sign_oca/user_signature/save",
            dict(params, signature=signature),
        )

    def test_save_writes_own_signature_only(self):
        """Un identifiant d'utilisateur glissé dans les paramètres est
        ignoré : seule la signature de la session change."""
        self.authenticate("sign_oca_profile_signer", "sign_oca_profile_signer")
        new_png = _image_base64((0, 0, 0, 255))
        result = self._save(
            self._png_uri(new_png),
            user_id=self.other_user.id,
            uid=self.other_user.id,
        )
        self.assertEqual(result, {"saved": True})
        self.assertEqual(self.signer_user.digital_signature, new_png)
        self.assertEqual(self.other_user.digital_signature, OTHER_PNG)

    def test_save_refuses_empty_or_unreadable_signature(self):
        self.authenticate("sign_oca_profile_signer", "sign_oca_profile_signer")
        svg = base64.b64encode(
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b"<script>alert(1)</script></svg>"
        ).decode()
        for signature in (
            "",
            "data:image/png;base64,",
            "bm90IGFuIGltYWdl",
            "data:image/svg+xml;base64," + svg,
        ):
            result = self._save(signature)
            self.assertTrue(result.get("error"), signature)
            self.assertEqual(
                self.signer_user.digital_signature, SIGNER_PNG, signature
            )

    def test_save_requires_a_session(self):
        response = self.url_open(
            "/sign_oca/user_signature/save",
            data=json.dumps(
                {"params": {"signature": self._png_uri(OTHER_PNG)}}
            ),
            headers={"Content-Type": "application/json"},
        )
        self.assertIn("SessionExpired", response.text)
        self.assertEqual(self.signer_user.digital_signature, SIGNER_PNG)

    # Le parcours dans le navigateur

    def _browser(self, steps, login=None):
        code = BROWSER_CODE % {"item": self.item["id"], "steps": steps}
        self.browser_js(self.signer.access_url, code, login=login)

    def test_browser_adopt_own_signature_and_sign(self):
        """« Adopt my signature » remplit la case sans dessin ; le document
        se signe ensuite avec cette image."""
        self._browser(
            """
            const adopt = await waitFor(
                () => document.querySelector(
                    ".modal .o_user_signature_sign_oca_adopt"
                ),
                "adopt button"
            );
            adopt.click();
            await waitFor(
                () => field()?.querySelector("img[src^='data:image/png']"),
                "filled field"
            );
            const sign = await waitFor(
                () => document.querySelector("#sign_oca_button:enabled"),
                "sign button"
            );
            window.addEventListener("beforeunload", () =>
                console.log("test successful")
            );
            sign.click();
            """,
            login="sign_oca_profile_signer",
        )
        self.assertTrue(self.signer.signed_on)
        value = self.sign_request.signatory_data[str(self.item["id"])]["value"]
        self.assertEqual(value, self._png_uri(SIGNER_PNG))

    def test_browser_save_drawn_signature(self):
        """La signature dessinée, « Save as my signature » cochée, remplace
        celle du profil et remplit la case."""
        self._browser(
            """
            const save = await waitFor(
                () => document.querySelector(
                    ".modal .o_user_signature_sign_oca_save"
                ),
                "save checkbox"
            );
            save.click();
            const confirm = await waitFor(
                () => document.querySelector(
                    ".modal .modal-footer .btn-primary:enabled"
                ),
                "drawn signature"
            );
            confirm.click();
            await waitFor(
                () => field()?.querySelector("img[src^='data:image/png']"),
                "filled field"
            );
            console.log("test successful");
            """,
            login="sign_oca_profile_signer",
        )
        signature = self.signer_user.digital_signature
        self.assertTrue(signature)
        self.assertNotEqual(signature, SIGNER_PNG)
        self.assertEqual(
            Image.open(io.BytesIO(base64.b64decode(signature))).format, "PNG"
        )
        self.assertEqual(self.other_user.digital_signature, OTHER_PNG)

    def test_browser_anonymous_signer_keeps_sign_oca_dialog(self):
        self._browser(
            """
            await waitFor(
                () => document.querySelector(".modal .modal-footer"),
                "dialog footer"
            );
            if (document.querySelector(
                ".modal .o_user_signature_sign_oca_adopt, "
                + ".modal .o_user_signature_sign_oca_save"
            )) {
                throw new Error("profile signature offered anonymously");
            }
            console.log("test successful");
            """
        )

    def test_browser_dialog_in_fr_ca(self):
        """La page suit la langue du signataire : la fenêtre s'affiche avec
        les traductions fr_CA du module."""
        self.env["res.lang"]._activate_lang("fr_CA")
        self.env["ir.module.module"]._load_module_terms(
            ["erplibre_user_signature_sign_oca"], ["fr_CA"], overwrite=True
        )
        self.signer_user.partner_id.lang = "fr_CA"
        self._browser(
            """
            const adopt = await waitFor(
                () => document.querySelector(
                    ".modal .o_user_signature_sign_oca_adopt"
                ),
                "adopt button"
            );
            const save = document.querySelector(".modal .form-check-label");
            if (
                adopt.textContent.trim() !== "Adopter ma signature"
                || save.textContent.trim() !== "Enregistrer comme ma signature"
            ) {
                throw new Error("Untranslated: " + adopt.textContent);
            }
            console.log("test successful");
            """,
            login="sign_oca_profile_signer",
        )
