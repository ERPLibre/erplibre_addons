#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

import logging
import os
from datetime import datetime, timedelta, timezone

import requests
import tldextract

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)
try:
    import cloudflare
except ImportError:
    _logger.warning(
        "`cloudflare` Python module not found, erplibre_website_cloudflare_nginx disabled."
    )
    cloudflare = None


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

    def action_cloudflare_set_website_dns(self):
        cloudflare_enable = self.env["ir.config_parameter"].get_param(
            "erplibre_website_cloudflare_nginx.cloudflare_enabled", ""
        )
        if not cloudflare_enable:
            return
        token = self.env["ir.config_parameter"].get_param(
            "erplibre_website_cloudflare_nginx.cloudflare_client_token", ""
        )
        if not token:
            raise ValidationError(_("Missing cloudflare token."))
        public_ip = self.env["ir.config_parameter"].get_param(
            "erplibre_website_cloudflare_nginx.cloudflare_public_ip", ""
        )
        if not public_ip:
            raise ValidationError(_("Missing public ip to configure DNS."))
        if not self.website_id:
            raise ValidationError(
                _("Missing website, create or select a website.")
            )
        website_domain = self.website_id.domain
        if not website_domain:
            raise ValidationError(_("Need a domain to configure your DNS."))
        if not cloudflare:
            raise ValidationError(
                _(
                    "Your python virtual environnement need cloudflare to be installed."
                )
            )
        cf = cloudflare.Cloudflare(api_token=token)
        url_extract = tldextract.extract(website_domain)
        url_domain_only = url_extract.top_domain_under_public_suffix
        domain_to_create = url_extract.fqdn
        zones = [a for a in cf.zones.list() if a.name == url_domain_only]
        if not zones:
            raise ValidationError(
                _("Cannot found domain %s on your cloudflare account.")
                % url_domain_only
            )
        zone = zones[0]
        # id_zone = zone.account.id
        id_zone = zone.id
        # List existing, create if not exist, or edit it with notes
        do_update_comment = False
        # Comment is limited to 100 char
        records_dns = cf.dns.records.list(
            zone_id=id_zone, content=public_ip, name=domain_to_create
        )
        lst_dns = [a for a in records_dns]
        if lst_dns:
            if do_update_comment:
                for dns in lst_dns:
                    # update comment
                    comment = dns.comment
                    new_comment = "Updated by %s at %s" % (
                        self.env.user.email,
                        datetime.now(timezone.utc),
                    )
                    if comment:
                        comment += "\n" + new_comment
                    else:
                        comment = new_comment
                    try:
                        record_response = cf.dns.records.edit(
                            zone_id=id_zone,
                            dns_record_id=dns.id,
                            name=domain_to_create,
                            type="A",
                            comment=comment,
                        )
                    except Exception as e:
                        raise ValidationError(e)
                    # print(record_response)
        else:
            try:
                record_response = cf.dns.records.create(
                    zone_id=id_zone,
                    name=domain_to_create,
                    type="A",
                    content=public_ip,
                    comment="Generated with Odoo by user %s at %s"
                    % (
                        self.env.user.email,
                        datetime.now(timezone.utc),
                    ),
                )
            except Exception as e:
                raise ValidationError(e)
            # print(record_response)

        os.system(
            "./script/nginx/deploy_nginx_and_cerbot.py --generate_nginx --run_certbot --domain %s"
            % domain_to_create
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
