# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Le cachet dessiné autour d'une signature, et le code qui l'identifie."""

import json
from base64 import b64decode
from hashlib import sha256
from io import BytesIO

import pytz
from odoo import fields, models
from odoo.tools.pdf import PdfFileReader
from reportlab.pdfgen import canvas

from ..tools import stamp_drawing

# Ordre des lignes sous la signature, de haut en bas ; chaque nom répond à
# un champ ``sign_stamp_show_<nom>`` de la société.
LINE_ORDER = ("name", "role", "date", "code")
# Clé de ``cr.cache`` sous laquelle ``_prepare_sign_items`` laisse, par
# signataire, les cases qu'il remplit dans la transaction.
SIGN_ITEMS_CACHE = "erplibre_sign_oca_signature_stamp.items"
# Caractères du code imprimés sur le PDF, groupés par 4.
PRINTED_CODE_LENGTH = 16


def _image_bytes(value):
    """Rend les octets de l'image d'une case de signature : du base64, nu
    ou en URI de données, au remplissage éventuellement absent."""
    encoded = value.split(",", 1)[1] if "," in value else value
    return b64decode(encoded + "=" * (-len(encoded) % 4))


class SignOcaRequest(models.Model):
    _inherit = "sign.oca.request"

    signature_code = fields.Char(
        compute="_compute_signature_code",
        search="_search_signature_code",
        help="Search the request whose signer printed this code; the 16 "
        "characters of the document are enough, spaces are ignored.",
    )

    def _compute_signature_code(self):
        for sign_request in self:
            sign_request.signature_code = False

    def _search_signature_code(self, operator, value):
        """Retrouve les demandes dont un signataire a un ``stamp_code`` qui
        commence par ``value``, espaces retirés et casse ignorée."""
        if operator not in ("=", "ilike") or not isinstance(value, str):
            raise NotImplementedError(operator)
        prefix = "".join(value.split()).lower()
        if not prefix:
            return [("id", "=", 0)]
        return [("signer_ids.stamp_code", "=like", prefix + "%")]

    def _get_sign_stamp_settings(self):
        """Rend le cachet que portent les signatures de cette demande, ou
        None quand elles n'en portent pas.

        Le ``sign_stamp_policy`` du modèle décide s'il y a un cachet ; sans
        modèle, ou à « As the company », c'est ``sign_stamp_enabled`` de la
        société de la demande. Le contenu vient toujours de la société.

        Les champs de sélection ajoutés ne sont pas obligatoires : un module
        testé pendant sa mise à jour crée des sociétés et des modèles sans
        les connaître. Une sélection vide vaut donc son défaut.

        :return: dict ``frame`` (bool), ``lines`` (noms de ``LINE_ORDER``
            activés), ``placement`` et ``colors`` ; None aussi quand le
            cachet n'a ni cadre ni ligne
        """
        self.ensure_one()
        policy = self.template_id.sign_stamp_policy or "company"
        company = self.company_id
        if policy == "disabled" or (
            policy == "company" and not company.sign_stamp_enabled
        ):
            return None
        lines = [
            name for name in LINE_ORDER if company[f"sign_stamp_show_{name}"]
        ]
        if not lines and not company.sign_stamp_frame:
            return None
        return {
            "frame": company.sign_stamp_frame,
            "lines": lines,
            "placement": company.sign_stamp_placement or "inside",
            "colors": company._get_sign_stamp_colors(),
        }

    def _get_sign_stamp_layout(self, item, box):
        """Rend ``(réglage, géométrie)`` du cachet de ``item`` sur une page
        de media box ``box``, ou ``(None, None)`` quand ``item`` n'est pas
        une case de signature ou que la demande n'a pas de cachet.

        La case est celle que sign_oca calcule pour dessiner ``item`` ; la
        géométrie est celle de ``stamp_drawing.layout``.
        """
        self.ensure_one()
        if item.get("field_type") != "signature":
            return None, None
        settings = self._get_sign_stamp_settings()
        if not settings:
            return None, None
        page_width = float(box.getWidth())
        page_height = float(box.getHeight())
        geometry = stamp_drawing.layout(
            item["position_x"] / 100 * page_width,
            (100 - item["position_y"] - item["height"]) / 100 * page_height,
            item["width"] / 100 * page_width,
            item["height"] / 100 * page_height,
            len(settings["lines"]),
            settings["frame"],
            settings["placement"],
        )
        return settings, geometry


class SignOcaRequestSigner(models.Model):
    _inherit = "sign.oca.request.signer"

    stamp_code = fields.Char(
        string="Signature Code",
        readonly=True,
        copy=False,
        index=True,
        help="SHA-256 of the signature images, the signer, the role, the "
        "signing date and the document as it stood before this signature. "
        "The stamp prints its first 16 characters.",
    )

    def _get_server_fields(self):
        return super()._get_server_fields() | {"stamp_code"}

    def _prepare_sign_items(self, items):
        """Garde dans ``cr.cache`` les cases que remplit ce signataire.

        Le dict rendu est celui que ``_stamp_pdf`` reçoit : un module qui
        change une valeur après ce ``super()`` change aussi ce que lit
        ``_get_stamp_code``, qui ne s'exécute qu'au dessin.
        """
        role_items = super()._prepare_sign_items(items)
        self.env.cr.cache.setdefault(SIGN_ITEMS_CACHE, {})[
            self.id
        ] = role_items
        return role_items

    def _get_stamp_code(self, item):
        """Rend le ``stamp_code`` de ce signataire ; le calcule et l'écrit
        au premier appel.

        Le code est le SHA-256 d'un JSON trié qui porte la demande, le
        signataire, son partenaire et son rôle, ``signed_on``, le SHA-256 du
        document tel qu'il est avant ce dessin, et le SHA-256 trié de chaque
        image de signature que ce signataire pose. Les images sont celles que
        ``_prepare_sign_items`` a gardées dans la transaction, sinon celle de
        ``item`` seul.

        Il s'appelle depuis ``_get_pdf_page_signature``, donc après tous les
        ``_prepare_sign_items`` : le partenaire est déjà celui qui signe.
        """
        self.ensure_one()
        if self.stamp_code:
            return self.stamp_code
        sign_request = self.request_id
        role_items = self.env.cr.cache.get(SIGN_ITEMS_CACHE, {}).get(self.id)
        images = sorted(
            sha256(_image_bytes(signed["value"])).hexdigest()
            for signed in (role_items or {"item": item}).values()
            if signed.get("field_type") == "signature" and signed.get("value")
        )
        document = sha256(b64decode(sign_request.data or b"")).hexdigest()
        payload = {
            "request": sign_request.id,
            "signer": self.id,
            "partner": self.partner_id.id,
            "role": self.role_id.id,
            "signed_on": fields.Datetime.to_string(self.signed_on),
            "document": document,
            "images": images,
        }
        code = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.sudo().stamp_code = code
        return code

    def _get_stamp_date(self):
        """Rend ``signed_on`` en ``AAAA-MM-JJ HH:MM ZZZ``, dans le fuseau du
        signataire, sinon celui de la société de la demande, sinon UTC.
        Sans ``signed_on``, l'heure courante."""
        self.ensure_one()
        tz_name = (
            self.partner_id.tz
            or self.request_id.company_id.partner_id.tz
            or "UTC"
        )
        moment = pytz.utc.localize(self.signed_on or fields.Datetime.now())
        return moment.astimezone(pytz.timezone(tz_name)).strftime(
            "%Y-%m-%d %H:%M %Z"
        )

    def _get_stamp_lines(self, item, settings):
        """Rend les lignes ``(texte, monospace)`` du cachet de ``item``,
        dans l'ordre de ``LINE_ORDER``, pour celles que ``settings`` active."""
        self.ensure_one()
        lines = []
        for name in settings["lines"]:
            if name == "name":
                lines.append((self.partner_id.name or "", False))
            elif name == "role":
                lines.append((self.role_id.name or "", False))
            elif name == "date":
                lines.append((self._get_stamp_date(), False))
            elif name == "code":
                code = self._get_stamp_code(item)[:PRINTED_CODE_LENGTH]
                grouped = " ".join(
                    code[i : i + 4] for i in range(0, len(code), 4)
                )
                lines.append((self.env._("Code %s", grouped), True))
        return lines

    def _get_pdf_page_signature(self, item, box):
        """Dessine la case de signature ``item`` avec son cachet quand la
        demande en porte un, sinon comme sign_oca.

        Le code est calculé même quand sa ligne n'est pas imprimée : il
        reste sur le signataire pour une vérification.
        """
        if not self or not item.get("value"):
            return super()._get_pdf_page_signature(item, box)
        self.ensure_one()
        settings, geometry = self.request_id._get_sign_stamp_layout(item, box)
        if not settings:
            return super()._get_pdf_page_signature(item, box)
        self._get_stamp_code(item)
        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=(box.getWidth(), box.getHeight()))
        stamp_drawing.draw(
            can,
            geometry,
            _image_bytes(item["value"]),
            self._get_stamp_lines(item, settings),
            settings["colors"],
            settings["frame"],
        )
        can.save()
        packet.seek(0)
        return PdfFileReader(packet).getPage(0)
