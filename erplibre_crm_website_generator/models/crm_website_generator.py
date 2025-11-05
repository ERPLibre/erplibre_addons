#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import re
import unicodedata

from odoo import _, api, fields, models


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
    website_domain_complete = fields.Char(
        compute="_compute_website_domain_complete"
    )
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
    product_to_copy_ids = fields.Many2many(comodel_name="product.product")

    def action_generate_website(self):
        for rec in self:
            if not rec.website_id:
                new_website = rec.env["website"].create(
                    {
                        "name": rec.name,
                        "domain": rec.website_domain_complete,
                        "company_id": rec.lead_id.company_id.id
                        or rec.env.company.id,
                    }
                )
                rec.website_id = new_website.id

                # Duplicating product
                if rec.product_to_copy_ids:
                    for product_id in rec.product_to_copy_ids:
                        product_copied_id = product_id.copy()
                        product_copied_id.website_id = rec.website_id.id
                        str_copy_to_detect = " (copie)"
                        if product_copied_id.name.endswith(str_copy_to_detect):
                            product_copied_id.name = product_copied_id.name[
                                : -len(str_copy_to_detect)
                            ]

                # TODO: Add logic to create the website content (pages, templates, etc.)
                # TODO fait son domaine cloudflare selon paramètre généraux

                cloudflare_enabled = (
                    rec.env["ir.config_parameter"]
                    .sudo()
                    .get_param(
                        "erplibre_website_cloudflare_nginx.cloudflare_enabled"
                    )
                )
                if cloudflare_enabled:
                    # TODO how to pass new_website to res.config.settings? Il faut le mettre dans un dictionnaire et l'activer.
                    # rec.env["res.config.settings"].create({"website_id": new_website.id}).execute().action_cloudflare_set_website_dns()
                    # rec.env["res.config.settings"].create({"website_id": new_website.id}).execute().action_cloudflare_set_website_dns()
                    new_website.action_cloudflare_set_website_dns()

                nginx_enabled = (
                    rec.env["ir.config_parameter"]
                    .sudo()
                    .get_param(
                        "erplibre_website_cloudflare_nginx.nginx_enabled"
                    )
                )
                if nginx_enabled:
                    # rec.env["res.config.settings"].create({"website_id": new_website.id}).action_nginx_set_website_dns()
                    new_website.action_nginx_set_website_dns()
                    # rec.env["res.config.settings"].create({"website_id": new_website.id}).action_nginx_set_website_dns()
                    # rec.env["res.config.settings"].sudo().action_nginx_set_website_dns()

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

                normalize_sub_domain = unicodedata.normalize(
                    "NFD", rec.website_sub_domain.lower()
                )
                website_sub_domain = re.sub(
                    r"[^a-z]", "", normalize_sub_domain
                )

                rec.website_url = (
                    f"{http}{website_sub_domain}.{rec.website_domain}"
                )

            else:
                rec.website_url = ""

    @api.depends("website_domain", "website_sub_domain")
    def _compute_website_domain_complete(self):
        for rec in self:
            normalize_sub_domain = unicodedata.normalize(
                "NFD", rec.website_sub_domain.lower()
            )
            website_sub_domain = re.sub(r"[^a-z]", "", normalize_sub_domain)
            rec.website_domain_complete = (
                website_sub_domain + "." + rec.website_domain
            )
