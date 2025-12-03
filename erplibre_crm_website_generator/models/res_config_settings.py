#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

try:
    import tldextract
except ImportError:
    tldextract = None

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    website_generator_base_domain = fields.Char(
        string="Base domain website generator",
        config_parameter="erplibre_crm_website_generator.website_generator_base_domain",
        readonly=False,
    )

    def set_values(self):
        super(ResConfigSettings, self).set_values()

        self.env["ir.config_parameter"].sudo().set_param(
            "erplibre_crm_website_generator.website_generator_base_domain",
            self.website_generator_base_domain or "",
        )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()

        website_generator_base_domain = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "erplibre_crm_website_generator.website_generator_base_domain"
            )
        )

        if not website_generator_base_domain:
            website_url = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("web.base.url")
            )
            url_extract = tldextract.extract(website_url)
            website_generator_base_domain = (
                url_extract.top_domain_under_public_suffix
            )

        res.update(
            website_generator_base_domain=website_generator_base_domain,
        )

        return res
