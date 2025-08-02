# Copyright 2025 TechnoLibre inc.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from poetry.console.commands import self

from odoo import _, api, fields, models


class CrmWebsiteGenerator(models.TransientModel):
    _name = "crm.website.generator.wizard"
    _description = "Website Generator from CRM lead"

    lead_id = fields.Many2one("crm.lead", string="Lead", required=True)
    nb_website_to_generate = fields.Integer(
        default=1, help="Will generate more website plan."
    )
    force_to_generate = fields.Boolean(
        help="Will generate website immediately."
    )
    use_generic_name = fields.Boolean(
        default=True,
        help="Will generate a random name, instead using crm leads name.",
    )
    website_name_generated = fields.Char()
    website_name = fields.Char()
    website_sub_domain = fields.Char()
    website_domain = fields.Char(
        string="Website Domain",
        default=lambda self: self.env["ir.config_parameter"]
        .sudo()
        .get_param(
            "erplibre_crm_website_generator.website_generator_base_domain"
        ),
    )
    website_url = fields.Char(
        string="Website URL", compute="_compute_website_url"
    )

    def action_confirm_generate_website(self):
        self.ensure_one()

        website_generator_ids = self.env["crm.website.generator"]
        website_generator_id = None
        for i in range(self.nb_website_to_generate):
            prefix_domain = ""
            if self.nb_website_to_generate > 1:
                prefix_domain = str(i + 1).zfill(
                    len(str(self.nb_website_to_generate))
                )
            website_generator_values = {
                "lead_id": self.lead_id.id,
                "company_id": self.lead_id.company_id.id
                or self.env.company.id,
                "website_domain": self.website_domain,
                "website_sub_domain": self.website_sub_domain + prefix_domain,
                "enable_custom_domain": not self.use_generic_name,
            }
            if self.use_generic_name:
                website_generator_values["name"] = (
                    self.website_name_generated + prefix_domain
                )
            else:
                website_generator_values["name"] = self.website_name
            website_generator_id = self.env["crm.website.generator"].create(
                website_generator_values
            )
            website_generator_ids += website_generator_id
            if self.force_to_generate:
                # TODO manage error, because it's a generator, or use external event
                # TODO put external event from parameter
                try:
                    website_generator_ids.action_generate_website()
                except Exception as e:
                    # TODO put into log
                    # TODO fetch log from remote
                    print(e)

        if self.nb_website_to_generate == 1 and website_generator_id:
            return {
                "name": _("Generate website from opportunity"),
                "type": "ir.actions.act_window",
                "view_mode": "form",
                "res_model": "crm.website.generator",
                "res_id": website_generator_id.id,
                "context": self.env.context,
            }
        else:
            return {
                "name": _("Generate website from opportunity"),
                "type": "ir.actions.act_window",
                "view_mode": "tree,form",
                "res_model": "crm.website.generator",
                "domain": [("id", "in", website_generator_ids.ids)],
                "context": self.env.context,
            }

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
