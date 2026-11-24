# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Light and dark themes of the web client (LU-NF-054, T-56): the dark
tints of every installed LinkUp module reach web.assets_web_dark only, the
dark bundle compiles, and the cookie ``color_scheme=dark`` serves it to a
member; the public pages load their stylesheet from the frontend bundle."""

from odoo.tests import HttpCase, tagged

from .common import DARK_COOKIES, MEMBER

# The modules whose static files style the web client, when installed.
LINKUP_MODULES = (
    "mail_linkup_reflet",
    "mail_linkup_gamification",
    "mail_linkup_network",
    "mail_linkup_community",
)


@tagged("post_install", "-at_install")
class TestLinkupThemeBundles(HttpCase):
    def _paths(self, bundle):
        params = self.env["ir.asset"]._get_asset_params()
        return [
            path
            for path, *_rest in self.env["ir.asset"]._get_asset_paths(
                bundle, params
            )
        ]

    def _installed(self):
        return (
            self.env["ir.module.module"]
            .search(
                [
                    ("name", "in", LINKUP_MODULES),
                    ("state", "=", "installed"),
                ]
            )
            .mapped("name")
        )

    def test_dark_files_in_dark_bundle_only(self):
        """Each installed module has dark tints, all of them in
        web.assets_web_dark and none in web.assets_backend."""
        backend = self._paths("web.assets_backend")
        dark = self._paths("web.assets_web_dark")
        for module in self._installed():
            prefix = f"/{module}/static/src/"
            dark_files = [
                path
                for path in dark
                if path.startswith(prefix) and path.endswith(".dark.scss")
            ]
            self.assertTrue(dark_files, module)
            self.assertFalse(
                [
                    path
                    for path in backend
                    if path.startswith(prefix) and path.endswith(".dark.scss")
                ],
                module,
            )
            # The light rules are in the dark bundle too: it includes
            # web.assets_web, then adds the tints.
            self.assertTrue(
                [
                    path
                    for path in dark
                    if path.startswith(prefix)
                    and path.endswith(".scss")
                    and not path.endswith(".dark.scss")
                ],
                module,
            )

    def test_public_stylesheet_in_frontend_only(self):
        """The rules of the public pages are in the frontend bundle, not
        in the web client."""
        public = "/mail_linkup_reflet/static/src/public/linkup_public.scss"
        self.assertIn(public, self._paths("web.assets_frontend"))
        self.assertNotIn(public, self._paths("web.assets_backend"))

    def test_dark_bundle_compiles(self):
        """The SCSS of the dark bundle compiles without error, with the
        rules of the light theme and the tints of the dark one."""
        bundle = self.env["ir.qweb"]._get_asset_bundle(
            "web.assets_web_dark", js=False
        )
        css = bundle.preprocess_css()
        self.assertFalse(bundle.css_errors)
        self.assertIn(".o-linkup-RefletCard", css)
        # The focus ring of the light rules, then its colour of the dark
        # tints: the same selector twice.
        self.assertGreaterEqual(
            css.count('[class*="o-linkup-"]:where(button, a, summary'), 2
        )

    def test_cookie_serves_dark_bundle(self):
        """A member with the cookie receives web.assets_web_dark in place
        of web.assets_web; without it, the light bundle."""
        self.env["res.users"].create(
            {
                "name": "Thème",
                "login": "linkup_theme_member",
                "password": "linkup_theme_member",
                "email": "linkup_theme_member@example.com",
                "groups_id": [(6, 0, [self.env.ref(MEMBER).id])],
            }
        )
        self.authenticate("linkup_theme_member", "linkup_theme_member")
        light = self.url_open("/odoo").text
        self.assertIn("web.assets_web.", light)
        self.assertNotIn("web.assets_web_dark", light)
        self.opener.cookies.update(DARK_COOKIES)
        dark = self.url_open("/odoo").text
        self.assertIn("web.assets_web_dark", dark)
