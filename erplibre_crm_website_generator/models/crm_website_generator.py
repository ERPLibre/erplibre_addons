#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import tldextract

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class WebsiteGenerator(models.Model):
    _name = "crm.website.generator"
    _description = "Website Generator from CRM Lead"

    name = fields.Char(string="Website Name")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    lead_id = fields.Many2one("crm.lead", string="Lead", ondelete="cascade")
    website_domain = fields.Char(
        string="Website Domain",
        default=lambda self: self.env["ir.config_parameter"]
        .sudo()
        .get_param(
            "erplibre_crm_website_generator.website_generator_base_domain"
        ),
    )
    website_sub_domain = fields.Char(string="Website Sub Domain")
    enable_custom_domain = fields.Boolean(
        help="Permit user to change the domain."
    )
    website_url = fields.Char(
        string="Website URL", compute="_compute_website_url"
    )
    website_id = fields.Many2one("website", string="Website")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("generated", "Generated"),
        ],
        string="Status",
        default="draft",
        compute="_compute_state",
    )

    def action_generate_website(self):
        self.ensure_one()

        if not self.website_id:
            new_website = self.env["website"].create(
                {
                    "name": self.name,
                    "domain": self.website_domain,
                    "company_id": self.lead_id.company_id.id
                    or self.env.company.id,
                }
            )
            self.website_id = new_website.id
            # self.state = "generated"

            # TODO: Add logic to create the website content (pages, templates, etc.)

    @api.depends("website_id")
    def _compute_state(self):
        for rec in self:
            rec.state = "generated" if rec.website_id else "draft"

    @api.depends("website_sub_domain", "website_domain")
    def _compute_website_url(self):
        for rec in self:
            if rec.website_sub_domain and rec.website_domain:
                actuel_url = (
                    self.env["ir.config_parameter"]
                    .sudo()
                    .get_param("web.base.url")
                )
                http = (
                    "https://" if actuel_url.startswith("https") else "http://"
                )
                rec.website_url = (
                    f"{http}{rec.website_sub_domain}.{rec.website_domain}"
                )
            else:
                rec.website_url = ""
