# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Le cachet d'une signature scellée par sign_oca_pades."""

import base64
from io import BytesIO

from odoo.addons.base.tests.common import BaseCommon
from odoo.addons.erplibre_sign_oca_signature_stamp.tests.test_signature_stamp import (
    SIGNATURE,
)
from odoo.addons.sign_oca_pades.tests.test_sign_oca_pades import (
    make_certificate,
)
from odoo.tools import misc
from pyhanko.pdf_utils.reader import PdfFileReader as HankoPdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext


class TestSignatureStampPades(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with open(misc.file_path("sign_oca/tests/empty.pdf"), "rb") as pdf:
            cls.pdf = pdf.read()
        p12, cls.certificate, __ = make_certificate("Stamp seal", b"secret")
        cls.role = cls.env.ref("sign_oca.sign_role_customer")
        cls.partner = cls.env["res.partner"].create({"name": "Sealed Signer"})
        cls.env.company.write(
            {
                "sign_oca_pades_pkcs12": base64.b64encode(p12),
                "sign_oca_pades_pkcs12_password": "secret",
                "sign_stamp_enabled": True,
                "sign_stamp_frame": True,
                "sign_stamp_show_name": True,
                "sign_stamp_show_date": True,
                "sign_stamp_show_code": True,
            }
        )

    def _sign(self, placement):
        """Signe une demande d'une seule case avec le cachet en
        ``placement`` ; rend ``(signataire, document, case en points)``."""
        self.env.company.sign_stamp_placement = placement
        sign_request = self.env["sign.oca.request"].create(
            {
                "data": base64.b64encode(self.pdf),
                "name": "Sealed stamp",
                "signer_ids": [
                    (
                        0,
                        0,
                        {
                            "partner_id": self.partner.id,
                            "role_id": self.role.id,
                        },
                    )
                ],
            }
        )
        item = sign_request.add_item(
            {
                "field_id": self.env.ref("sign_oca.sign_field_signature").id,
                "role_id": self.role.id,
                "page": 1,
                "position_x": 10,
                "position_y": 20,
                "width": 40,
                "height": 12,
            }
        )
        sign_request.action_send()
        signer = sign_request.signer_ids
        signer.action_sign({str(item["id"]): dict(item, value=SIGNATURE)})
        document = base64.b64decode(sign_request.data)
        box = HankoPdfFileReader(BytesIO(document)).root["/Pages"]["/Kids"][0][
            "/MediaBox"
        ]
        width, height = float(box[2]), float(box[3])
        case = (0.1 * width, 0.68 * height, 0.4 * width, 0.12 * height)
        return signer, document, case

    def _signature(self, signer, document):
        """Valide chaque sceau de ``document`` et rend celui du champ de
        ``signer`` ; l'autre est le sceau final de la demande terminée."""
        signatures = HankoPdfFileReader(BytesIO(document)).embedded_signatures
        for signature in signatures:
            status = validate_pdf_signature(
                signature,
                signer_validation_context=ValidationContext(
                    trust_roots=[self.certificate], allow_fetching=False
                ),
            )
            self.assertTrue(status.bottom_line, signature.field_name)
        return next(
            signature
            for signature in signatures
            if signature.field_name == signer.pades_field_name
        )

    def _rect(self, signature):
        x1, y1, x2, y2 = (float(v) for v in signature.sig_field["/Rect"])
        return x1, y1, x2 - x1, y2 - y1

    def _appearance(self, signature):
        """Rend le contenu décodé de l'apparence du champ et de ses
        XObjects."""
        chunks = []
        todo = [signature.sig_field["/AP"]["/N"]]
        while todo:
            current = todo.pop()
            chunks.append(current.data)
            xobjects = current.get("/Resources", {}).get("/XObject", {})
            todo.extend(
                xobjects[name]
                for name in xobjects
                if xobjects[name].get("/Subtype") == "/Form"
            )
        return b"\n".join(chunks)

    def test_below_extends_the_signature_field(self):
        signer, document, case = self._sign("below")
        signature = self._signature(signer, document)
        x, y, width, height = self._rect(signature)
        self.assertAlmostEqual(x, case[0], places=1)
        self.assertAlmostEqual(width, case[2], places=1)
        self.assertAlmostEqual(y + height, case[1] + case[3], places=1)
        self.assertLess(y, case[1] - 10, "field extended under the box")
        appearance = self._appearance(signature)
        self.assertIn(b"Sealed Signer", appearance)
        self.assertIn(b"Code " + signer.stamp_code[:4].encode(), appearance)

    def test_inside_keeps_the_box(self):
        signer, document, case = self._sign("inside")
        signature = self._signature(signer, document)
        for measured, expected in zip(
            self._rect(signature), case, strict=True
        ):
            self.assertAlmostEqual(measured, expected, places=1)
