#!/usr/bin/env python3
# © 2021-2025 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import hashlib
import random
import re
import unicodedata
import uuid

from odoo import _, api, fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    website_generator_ids = fields.One2many(
        "crm.website.generator", "lead_id", string="Generated Websites"
    )
    website_generator_count = fields.Integer(
        string="Number of Websites", compute="_compute_website_generator_count"
    )

    @api.depends("website_generator_ids")
    def _compute_website_generator_count(self):
        for lead in self:
            lead.website_generator_count = len(lead.website_generator_ids)

    def action_get_website(self):
        return {
            "name": _("Generate website from opportunity"),
            "type": "ir.actions.act_window",
            "view_mode": "tree,form",
            "res_model": "crm.website.generator",
            "domain": [("id", "in", self.website_generator_ids.ids)],
            "context": self.env.context,
        }

    def action_create_website_plan(self):
        self.ensure_one()

        unique_string = str(uuid.uuid4())
        hashed_name = (
            hashlib.sha256(unique_string.encode("utf-8"))
            .hexdigest()[:5]
            .replace("-", "")
        )
        hashed_name = (
            chr(ord("a") + random.randint(0, 25)) + hashed_name
        ).lower()

        normalize_sub_domain = unicodedata.normalize("NFD", self.name.lower())
        website_sub_domain = re.sub(r"[^a-z]", "", normalize_sub_domain)
        website_generated_sub_domain = hashed_name
        website_generated_name = _("Website for ") + hashed_name

        return {
            "name": "Create Website generator",
            "type": "ir.actions.act_window",
            "res_model": "crm.website.generator.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_lead_id": self.id,
                "default_website_name_generated": website_generated_name,
                "default_website_name": _("Website for ") + self.name,
                "default_website_sub_domain": website_sub_domain,
                "default_website_sub_domain_generated": website_generated_sub_domain,
            },
        }
