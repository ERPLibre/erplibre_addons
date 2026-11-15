# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import ast

from lxml import etree
from odoo.addons.website.tools import MockRequest
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import hmac

MODULE = "erplibre_website_import_from_dolibarr"
SOCIAL = (
    "social_twitter social_facebook social_github social_linkedin"
    " social_youtube social_instagram social_tiktok"
).split()
# The values each template reads: what its caller sets, the request that
# Odoo provides, and the loop variables and locals the template defines.
TEMPLATE_NAMES = {
    "blog_post_list": {
        "blog_id",
        "blog_limit",
        "request",
        "max",
        "dolibarr_posts",
        "post",
    },
    "social_links": {"website", "field"},
    "contact_form": {"form_id"},
}
DIRECTIVES = {
    "t-set",
    "t-value",
    "t-foreach",
    "t-as",
    "t-if",
    "t-out",
    "t-field",
    "t-options",
}
# The fields a form of the module submits to mail.mail.
FORM_FIELDS = {"name", "email_from", "subject", "description", "email_to"}


def _attribute_chains(tree):
    """Dotted reads of an expression, as (name, attribute) pairs."""
    return {
        (node.value.id, node.attr)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
    }


@tagged("post_install", "-at_install")
class TestTemplates(TransactionCase):
    def arch_of(self, name):
        return etree.fromstring(
            self.env.ref("%s.%s" % (MODULE, name)).arch.encode()
        )

    def assert_arch_is_safe(self, name):
        """Every expression reads only the values the template names.

        No t-attf and no t-call; each expression parses as Python and
        names nothing but the template's own values and locals; a
        directive is one the templates are meant to use.
        """
        allowed = TEMPLATE_NAMES[name]
        for el in self.arch_of(name).iter():
            for attr, value in el.attrib.items():
                if not attr.startswith("t-") or attr == "t-name":
                    continue
                self.assertNotIn("t-attf", attr)
                self.assertNotEqual(attr, "t-call")
                self.assertTrue(
                    attr in DIRECTIVES or attr.startswith("t-att-"), attr
                )
                if attr == "t-as":
                    self.assertRegex(value, r"^[a-z_]+$")
                    continue
                tree = ast.parse(value, mode="eval")
                names = {
                    n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
                }
                self.assertLessEqual(names, allowed, value)
                for base, attribute in _attribute_chains(tree):
                    self.assertFalse(attribute.startswith("__"), value)

    def test_templates_read_only_their_own_values(self):
        for name in TEMPLATE_NAMES:
            self.assert_arch_is_safe(name)

    def test_contact_form_follows_odoo_form_snippet(self):
        arch = self.arch_of("contact_form")
        (form,) = arch.xpath("//form")
        self.assertEqual(form.get("action"), "/website/form/")
        self.assertEqual(form.get("method"), "post")
        self.assertEqual(form.get("data-model_name"), "mail.mail")
        self.assertEqual(form.get("data-success-page"), "/contactus-thank-you")
        names = {
            el.get("name") for el in arch.xpath("//input|//textarea|//select")
        }
        self.assertEqual(names, FORM_FIELDS)
        for el in arch.xpath("//*[@name]"):
            self.assertIsNone(el.get("t-att-name"))
            self.assertIsNone(el.get("t-att-value"))
        (email_to,) = arch.xpath("//input[@name='email_to']")
        self.assertEqual(email_to.get("type"), "hidden")
        self.assertEqual(email_to.get("value"), "")
        self.assertFalse(
            arch.xpath("//*[@name='email_cc' or @name='email_bcc']")
        )
        self.assertFalse(
            arch.xpath("//*[@t-att-action or @t-att-data-model_name]")
        )

    def test_contact_form_is_signed_for_the_company_address(self):
        # Odoo signs email_to when it combines the view; an empty value
        # is signed as the company address, never a source address.
        self.env.company.email = "info@example.org"
        view = self.env.ref("%s.contact_form" % MODULE)
        root = view._get_combined_arch()
        (signature,) = root.xpath("//input[@name='website_form_signature']")
        expected = hmac(
            self.env(su=True), "website_form_signature", "info@example.org"
        )
        self.assertEqual(signature.get("value"), expected)

    def test_contact_form_renders_with_its_form_id(self):
        html = str(
            self.env["ir.qweb"]._render(
                "%s.contact_form" % MODULE, {"form_id": "dolibarr_form_3"}
            )
        )
        root = etree.fromstring(html)
        (form,) = root.xpath("//form")
        self.assertEqual(form.get("id"), "dolibarr_form_3")
        self.assertIn("dolibarr_form_3_name", html)

    def test_social_links_loop_on_website_fields(self):
        vals = {field: False for field in SOCIAL}
        vals.update(
            name="Example social",
            social_facebook="https://www.example.org/fb",
        )
        website = self.env["website"].create(vals)
        html = str(
            self.env["ir.qweb"]._render(
                "%s.social_links" % MODULE, {"website": website}
            )
        )
        self.assertIn("https://www.example.org/fb", html)
        self.assertEqual(html.count("<li"), 1)

    def render_blog_list(self, blog, limit):
        website = self.env["website"].search([], limit=1)
        with MockRequest(self.env, website=website):
            return str(
                self.env["ir.qweb"]._render(
                    "%s.blog_post_list" % MODULE,
                    {"blog_id": blog.id, "blog_limit": limit},
                )
            )

    def test_blog_limit_is_at_least_one(self):
        blog = self.env["blog.blog"].create({"name": "Example blog"})
        other = self.env["blog.blog"].create({"name": "Other blog"})
        posts = self.env["blog.post"].create(
            [
                {
                    "name": "Post %d" % idx,
                    "blog_id": blog.id,
                    "is_published": True,
                    "post_date": "2026-01-0%d 10:00:00" % idx,
                }
                for idx in (1, 2, 3)
            ]
        )
        self.env["blog.post"].create(
            {"name": "Elsewhere", "blog_id": other.id, "is_published": True}
        )
        self.env["blog.post"].create(
            {"name": "Draft", "blog_id": blog.id, "is_published": False}
        )
        self.assertEqual(len(posts), 3)
        for limit in (0, -4, None):
            html = self.render_blog_list(blog, limit)
            self.assertEqual(html.count("<li"), 1, limit)
            self.assertIn("Post 3", html)
        html = self.render_blog_list(blog, 2)
        self.assertEqual(html.count("<li"), 2)
        self.assertIn("Post 3", html)
        self.assertIn("Post 2", html)
        self.assertNotIn("Post 1", html)
        html = self.render_blog_list(blog, 50)
        self.assertEqual(html.count("<li"), 3)
        for hidden in ("Elsewhere", "Draft"):
            self.assertNotIn(hidden, html)
