from odoo import _, models, fields, models, api, exceptions

class Contact(models.Model):
    _name = 'website.cv'
    _description = 'Website_CV'

    name = fields.Char(string='informations_name', required=True)
    address = fields.Char(string='informations_address', required=True)
    phone = fields.Char(string='informations_phone', required=True)
    email = fields.Char(string='informations_email', required=True)
    description = fields.Char(string='informations_description')

    @api.constrains('email')
    def _check_email(self):
        for record in self:
            if record.email and '@' not in record.email:
                raise exceptions.ValidationError("Invalid email format!")
