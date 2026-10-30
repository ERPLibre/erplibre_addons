# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Le cachet dessiné autour d'une signature de sign_oca, et son code."""

import base64
import io
import json
from datetime import datetime
from hashlib import sha256
from unittest.mock import patch

from odoo.addons.base.tests.common import BaseCommon
from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user
from odoo.tools import misc
from odoo.tools.pdf import PdfFileReader
from PIL import Image

from ..tools import stamp_drawing


def _png_data_uri(color):
    """Rend une image PNG unie en URI de données, comme la case de
    signature de sign_oca l'envoie."""
    buffer = io.BytesIO()
    Image.new("RGBA", (60, 20), color).save(buffer, "PNG")
    return (
        "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    )


SIGNATURE = _png_data_uri((0, 0, 128, 255))
OTHER_SIGNATURE = _png_data_uri((128, 0, 0, 255))


class TestSignatureStamp(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(misc.file_path("sign_oca/tests/empty.pdf"), "rb") as pdf:
            cls.pdf = pdf.read()
        cls.role = cls.env.ref("sign_oca.sign_role_customer")
        cls.partner = cls.env["res.partner"].create(
            {"name": "Stamp Signer", "tz": "America/Toronto"}
        )
        cls.company = cls.env.company
        cls.company.write(
            {
                "sign_stamp_enabled": True,
                "sign_stamp_frame": True,
                "sign_stamp_show_date": True,
                "sign_stamp_show_code": True,
                "sign_stamp_show_name": False,
                "sign_stamp_show_role": False,
                "sign_stamp_placement": "inside",
                "sign_stamp_color_mode": "erplibre",
            }
        )

    def _request(self, template=False, partners=None):
        """Rend une demande envoyée, une case de signature par signataire,
        et les cases par signataire."""
        partners = partners or [self.partner]
        roles = [self.role] + [
            self.env["sign.oca.role"].create({"name": f"Role {index}"})
            for index in range(1, len(partners))
        ]
        sign_request = self.env["sign.oca.request"].create(
            {
                "data": base64.b64encode(self.pdf),
                "name": "Stamp test",
                "template_id": template and template.id,
                "signer_ids": [
                    (0, 0, {"partner_id": partner.id, "role_id": role.id})
                    for partner, role in zip(partners, roles, strict=True)
                ],
            }
        )
        items = {}
        for index, role in enumerate(roles):
            items[role] = sign_request.add_item(
                {
                    "field_id": self.env.ref(
                        "sign_oca.sign_field_signature"
                    ).id,
                    "role_id": role.id,
                    "page": 1,
                    "position_x": 10,
                    "position_y": 10 + 25 * index,
                    "width": 40,
                    "height": 15,
                }
            )
        sign_request.action_send()
        return sign_request, items

    def _sign(self, sign_request, items, role=None, value=SIGNATURE):
        role = role or self.role
        signer = sign_request.signer_ids.filtered(lambda s: s.role_id == role)
        item = items[role]
        signer.action_sign({str(item["id"]): dict(item, value=value)})
        return signer

    def _text(self, sign_request):
        reader = PdfFileReader(io.BytesIO(base64.b64decode(sign_request.data)))
        return reader.getPage(0).extract_text()

    def test_stamp_prints_date_and_code(self):
        sign_request, items = self._request()
        signer = self._sign(sign_request, items)
        self.assertRegex(signer.stamp_code, r"^[0-9a-f]{64}$")
        code = signer.stamp_code
        text = self._text(sign_request)
        grouped = " ".join(code[i : i + 4] for i in range(0, 16, 4))
        self.assertIn(f"Code {grouped}", text)
        self.assertRegex(text, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} E[SD]T")
        self.assertNotIn("Stamp Signer", text)

    def _expected_code(self, sign_request, signer, document, partner):
        """Rend le code que doit porter ``signer``, recalculé ici depuis ses
        entrées ; ``document`` est le SHA-256 d'avant la signature."""
        image = SIGNATURE.split(",", 1)[1]
        payload = {
            "request": sign_request.id,
            "signer": signer.id,
            "partner": partner.id,
            "role": self.role.id,
            "signed_on": signer.signed_on.strftime("%Y-%m-%d %H:%M:%S"),
            "document": document,
            "images": [sha256(base64.b64decode(image)).hexdigest()],
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def test_code_is_sha256_of_its_inputs(self):
        sign_request, items = self._request()
        document = sha256(base64.b64decode(sign_request.data)).hexdigest()
        signer = self._sign(sign_request, items)
        self.assertEqual(
            signer.stamp_code,
            self._expected_code(sign_request, signer, document, self.partner),
        )

    def test_partner_changed_after_prepare_is_the_one_stamped(self):
        # Un module chargé après celui-ci, comme sign_oca_tier_validation,
        # change le partenaire après le ``super()`` de
        # ``_prepare_sign_items`` : le code et le nom suivent ce changement.
        self.company.sign_stamp_show_name = True
        taker = self.env["res.partner"].create({"name": "Tier Taker"})
        signer_class = type(self.env["sign.oca.request.signer"])
        prepare = signer_class._prepare_sign_items

        def take_role(signer, items):
            role_items = prepare(signer, items)
            signer.partner_id = taker
            return role_items

        sign_request, items = self._request()
        document = sha256(base64.b64decode(sign_request.data)).hexdigest()
        with patch.object(signer_class, "_prepare_sign_items", take_role):
            signer = self._sign(sign_request, items)
        self.assertEqual(signer.partner_id, taker)
        self.assertEqual(
            signer.stamp_code,
            self._expected_code(sign_request, signer, document, taker),
        )
        text = self._text(sign_request)
        self.assertIn("Tier Taker", text)
        self.assertNotIn("Stamp Signer", text)

    def test_each_signer_gets_its_own_code(self):
        other = self.env["res.partner"].create({"name": "Second Signer"})
        sign_request, items = self._request(partners=[self.partner, other])
        roles = list(items)
        first = self._sign(sign_request, items, roles[0])
        second = self._sign(sign_request, items, roles[1], OTHER_SIGNATURE)
        self.assertTrue(first.stamp_code and second.stamp_code)
        self.assertNotEqual(first.stamp_code, second.stamp_code)

    def test_lines_follow_the_settings(self):
        self.company.write(
            {
                "sign_stamp_show_name": True,
                "sign_stamp_show_role": True,
                "sign_stamp_show_date": False,
                "sign_stamp_show_code": False,
            }
        )
        sign_request, items = self._request()
        signer = self._sign(sign_request, items)
        text = self._text(sign_request)
        self.assertIn("Stamp Signer", text)
        self.assertIn(self.role.name, text)
        self.assertNotIn("Code ", text)
        self.assertNotRegex(text, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
        # Le code reste calculé pour une vérification.
        self.assertTrue(signer.stamp_code)

    def test_company_disabled_draws_as_sign_oca(self):
        self.company.sign_stamp_enabled = False
        sign_request, items = self._request()
        signer = self._sign(sign_request, items)
        self.assertFalse(signer.stamp_code)
        self.assertNotIn("Code ", self._text(sign_request))

    def test_template_policy_overrides_the_company(self):
        template = self.env["sign.oca.template"].create(
            {
                "name": "Stamp template",
                "data": base64.b64encode(self.pdf),
                "filename": "empty.pdf",
                "sign_stamp_policy": "disabled",
            }
        )
        sign_request, items = self._request(template=template)
        self.assertFalse(self._sign(sign_request, items).stamp_code)

        self.company.sign_stamp_enabled = False
        template.sign_stamp_policy = "enabled"
        sign_request, items = self._request(template=template)
        self.assertTrue(self._sign(sign_request, items).stamp_code)

    def test_search_by_printed_code(self):
        sign_request, items = self._request()
        signer = self._sign(sign_request, items)
        printed = " ".join(
            signer.stamp_code[i : i + 4].upper() for i in range(0, 16, 4)
        )
        found = self.env["sign.oca.request"].search(
            [("signature_code", "ilike", printed)]
        )
        self.assertEqual(found, sign_request)
        self.assertFalse(
            self.env["sign.oca.request"].search(
                [("signature_code", "=", "  ")]
            )
        )

    def test_stamp_code_is_a_server_field(self):
        sign_request, items = self._request()
        signer = self._sign(sign_request, items)
        user = new_test_user(
            self.env,
            login="stamp_admin",
            groups="sign_oca.sign_oca_group_admin",
        )
        with self.assertRaises(UserError):
            signer.with_user(user).write({"stamp_code": "0" * 64})

    def test_stamp_date_uses_the_signer_time_zone(self):
        sign_request, __ = self._request()
        signer = sign_request.signer_ids
        signer.sudo().signed_on = datetime(2026, 1, 15, 17, 30)
        self.assertEqual(signer._get_stamp_date(), "2026-01-15 12:30 EST")
        self.partner.tz = False
        self.company.partner_id.tz = False
        self.assertEqual(signer._get_stamp_date(), "2026-01-15 17:30 UTC")

    def test_colors_by_mode(self):
        company = self.company
        self.assertEqual(
            company._get_sign_stamp_colors(), stamp_drawing.ERPLIBRE_COLORS
        )
        company.write(
            {
                "sign_stamp_color_mode": "company",
                "primary_color": "#112233",
                "secondary_color": False,
            }
        )
        self.assertEqual(
            company._get_sign_stamp_colors(),
            ("#112233", stamp_drawing.ERPLIBRE_COLORS[1]),
        )
        company.write(
            {
                "sign_stamp_color_mode": "custom",
                "sign_stamp_color_1": "#abcdef",
                "sign_stamp_color_2": "#010203",
            }
        )
        self.assertEqual(
            company._get_sign_stamp_colors(), ("#abcdef", "#010203")
        )
        with self.assertRaises(ValidationError):
            company.sign_stamp_color_1 = "purple"


class TestStampLayout(BaseCommon):
    def test_inside_keeps_the_box(self):
        geometry = stamp_drawing.layout(100, 200, 160, 60, 2, True, "inside")
        self.assertEqual(geometry["outer"], (100, 200, 160, 60))
        x, y, width, height = geometry["image"]
        self.assertGreater(y, 200)
        self.assertLessEqual(y + height, 260)
        self.assertGreaterEqual(height, 60 * 0.4 - 2 * geometry["padding"])
        self.assertEqual(len(geometry["baselines"]), 2)
        self.assertTrue(all(200 < b < y for b in geometry["baselines"]))

    def test_inside_shrinks_the_font_of_a_short_box(self):
        geometry = stamp_drawing.layout(0, 0, 120, 24, 4, True, "inside")
        self.assertLess(geometry["font_size"], 4.5)
        self.assertGreaterEqual(geometry["font_size"], 3.0)

    def test_below_extends_under_the_box(self):
        geometry = stamp_drawing.layout(100, 200, 160, 60, 3, True, "below")
        x, y, width, height = geometry["outer"]
        self.assertEqual((x, width), (100, 160))
        self.assertLess(y, 200)
        self.assertAlmostEqual(y + height, 260)
        self.assertEqual(geometry["image"][1], 200)
        self.assertTrue(all(y < b < 200 for b in geometry["baselines"]))

    def test_below_without_lines_keeps_the_box(self):
        geometry = stamp_drawing.layout(100, 200, 160, 60, 0, True, "below")
        self.assertEqual(geometry["outer"], (100, 200, 160, 60))

    def test_no_frame_has_no_emblem(self):
        geometry = stamp_drawing.layout(0, 0, 160, 60, 1, False, "inside")
        self.assertIsNone(geometry["emblem"])
        self.assertLess(geometry["padding"], 1)
