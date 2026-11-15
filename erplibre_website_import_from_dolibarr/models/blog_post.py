# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import re

from odoo import api, fields, models

from ..dolibarr_site.urls import local_path

_COVER_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)", re.I)


class BlogPost(models.Model):
    _inherit = "blog.post"

    dolibarr_import_cover_url = fields.Char(
        compute="_compute_dolibarr_import_cover_url"
    )

    @api.depends("cover_properties")
    def _compute_dolibarr_import_cover_url(self):
        """Site path of the cover image, or "" when there is none.

        Blog editors can write any cover_properties, so the value is
        trusted only as a local path: callers place it in URL attributes.
        """
        for post in self:
            try:
                props = json.loads(post.cover_properties or "{}")
            except ValueError:
                props = {}
            image = (
                props.get("background-image")
                if isinstance(props, dict)
                else ""
            )
            match = (
                _COVER_URL.search(image) if isinstance(image, str) else None
            )
            post.dolibarr_import_cover_url = (
                local_path(match.group(1).strip()) if match else ""
            )

    def _check_for_publication(self, vals):
        """No chatter post per imported post, on create or publish.

        Only under the dolibarr_website_import context key; any other
        caller keeps the standard behaviour.
        """
        if self.env.context.get("dolibarr_website_import"):
            return False
        return super()._check_for_publication(vals)
