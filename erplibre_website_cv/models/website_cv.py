from odoo import _, models, fields, models, api, exceptions

class Contact(models.Model):
    _name = 'website.cv'
    _description = 'Website_CV'

    name = fields.Char(string='Name', required=True)
    address = fields.Char(string='Address', required=True)
    phone = fields.Char(string='Phone', required=True)
    email = fields.Char(string='Email', required=True)
    description = fields.Char(string='Description')

    @api.constrains('email')
    def _check_email(self):
        for record in self:
            if record.email and '@' not in record.email:
                raise exceptions.ValidationError("Invalid email format!")
