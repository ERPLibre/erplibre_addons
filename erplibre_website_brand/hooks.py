# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).


def post_init_hook(env):
    """Give the websites that exist before the install the default logo.

    The field default applies to websites created afterwards only: an
    attachment field has no column for the install to fill.
    """
    Website = env["website"]
    websites = Website.search([]).filtered(lambda w: not w.erplibre_signature_logo)
    websites.erplibre_signature_logo = Website._default_erplibre_signature_logo()
