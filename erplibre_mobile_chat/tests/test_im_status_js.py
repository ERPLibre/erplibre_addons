# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Suite hoot du module (static/tests), lancée dans Chrome sans tête par
le lanceur de tests d'Odoo ; sans Chrome, browser_js saute le test."""

from odoo.addons.web.tests.test_js import unit_test_error_checker
from odoo.tests import tagged
from odoo.tests.common import HttpCase

HOOT_SUITE = "@erplibre_mobile_chat"


def hoot_job_id(name):
    """Rend l'identifiant que hoot donne à la suite ou au test `name` (son
    nom complet), le même calcul que HOOTCommon._generate_hash d'Odoo : le
    paramètre `id` de /web/tests ne lance que cette suite."""
    value = 0
    for char in name:
        value = ((value << 5) - value + ord(char)) & 0xFFFFFFFF
    return f"{value:08x}"


@tagged("post_install", "-at_install")
class TestImStatusServicePatchJs(HttpCase):
    def test_hoot_suite(self):
        self.browser_js(
            "/web/tests?headless&loglevel=2&preset=desktop&timeout=15000"
            f"&id={hoot_job_id(HOOT_SUITE)}",
            "",
            "",
            login="admin",
            timeout=600,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
        )
