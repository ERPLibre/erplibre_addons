from odoo import _, api, fields, models

class WebsiteCV(models.Model):
    _name = "website.cv"
    _description = "website_cv"

    name = fields.Char()
