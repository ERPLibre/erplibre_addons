#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cloudflare_client_token = fields.Char(
        string="Cloudflare token",
        config_parameter="erplibre_website_cloudflare_nginx.cloudflare_client_token",
        readonly=False,
        default="",
    )

    cloudflare_public_ip = fields.Char(
        string="Cloudflare public ip",
        config_parameter="erplibre_website_cloudflare_nginx.cloudflare_public_ip",
        readonly=False,
        default="",
    )

    cloudflare_enabled = fields.Boolean(
        config_parameter="erplibre_website_cloudflare_nginx.cloudflare_enabled"
    )

    nginx_enabled = fields.Boolean(
        config_parameter="erplibre_website_cloudflare_nginx.nginx_enabled"
    )

    def action_cloudflare_auto_configure_public_ip(self):
        self.ensure_one()
        response = requests.get(r"https://api.ipify.org", timeout=5)
        response.raise_for_status()
        ip = response.text.strip()
        self.cloudflare_public_ip = ip
        self.env["ir.config_parameter"].set_param(
            "erplibre_website_cloudflare_nginx.cloudflare_public_ip", ip
        )

    def action_cloudflare_set_website_dns(self):
        if self.website_id:
            self.website_id.action_cloudflare_set_website_dns()

    def action_nginx_set_website_dns(self):
        if self.website_id:
            self.website_id.action_nginx_set_website_dns()
