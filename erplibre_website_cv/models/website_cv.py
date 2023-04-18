from odoo import _, models, fields, models, api, exceptions


class Contact(models.Model):
    _name = 'website.cv'
    _description = 'Website_CV'

    name = fields.Char(string='Nom', required=True)
    address = fields.Char(string='Address', required=True)
    phone = fields.Char(string='Téléphone', required=True)
    email = fields.Char(string='Courriel', required=True)
    description = fields.Char(string='Description', required=True)

    name_experience = fields.Char(string='Nom experience', required=True)
    entreprise_name_experience = fields.Char(
        string='Nom entreprise', required=True)
    description_experience = fields.Char(string='Description', required=True)
    date_experience = fields.Char(string='Date', required=True)

    name_projets = fields.Char(string='Nom projets', required=True)
    entreprise_name_projets = fields.Char(
        string='Nom entreprise', required=True)
    description_projets = fields.Char(string='Description', required=True)
    date_projets = fields.Char(string='Date', required=True)

    name_formations = fields.Char(string='Nom formations', required=True)
    entreprise_name_formations = fields.Char(
        string='Nom entreprise', required=True)
    description_formations = fields.Char(string='Description', required=True)
    date_formations = fields.Char(string='Date', required=True)

    @api.constrains('email')
    def _check_email(self):
        for record in self:
            if record.email and '@' not in record.email:
                raise exceptions.ValidationError("Invalid email format!")

    @api.onchange('phone')
    def _onchange_phone(self):
        for record in self:
            if record.phone:
                phone_digits = ''.join(filter(str.isdigit, record.phone))
                formatted_phone = '({}) {}-{}'.format(
                    phone_digits[:3], phone_digits[3:6], phone_digits[6:])
                record.phone = formatted_phone
