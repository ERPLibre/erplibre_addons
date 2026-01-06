#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
from odoo import _, api, fields, models


class DevopsSystemNginxSiteConfTemplate(models.Model):
    _name = "devops.system.nginx.site.conf.template"
    _description = "devops_system_nginx_site_conf_template"
    _order = "id"

    name = fields.Char()

    file_content = fields.Text()
