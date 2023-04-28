from odoo import _, api, exceptions, fields, models


class Contact(models.Model):
    _name = "website.cv"
    _description = "Website_CV"

    name = fields.Char(string="Nom")
    address = fields.Char(string="Address")
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="Courriel")
    description = fields.Char(string="Description")

    name_experience = fields.Char(string="Nom experience")
    entreprise_name_experience = fields.Char(
        string="Nom entreprise"
    )
    description_experience = fields.Char(string="Description")
    date_experience = fields.Char(string="Date")

    name_projets = fields.Char(string="Nom projets")
    entreprise_name_projets = fields.Char(
        string="Nom entreprise"
    )
    description_projets = fields.Char(string="Description")
    date_projets = fields.Char(string="Date")

    name_formations = fields.Char(string="Nom formations")
    entreprise_name_formations = fields.Char(
        string="Nom entreprise"
    )
    description_formations = fields.Char(string="Description")
    date_formations = fields.Char(string="Date")

    name_interets = fields.Char(string="Nom interets")
    description_interets = fields.Char(string="Description")

    name_trophes = fields.Char(string="Nom trophes")
    date_trophes = fields.Char(string="Date")

    @api.constrains("email")
    def _check_email(self):
        for record in self:
            if record.email and "@" not in record.email:
                raise exceptions.ValidationError("Invalid email format!")

    @api.onchange("phone")
    def _onchange_phone(self):
        for record in self:
            if record.phone:
                phone_digits = "".join(filter(str.isdigit, record.phone))
                formatted_phone = "({}) {}-{}".format(
                    phone_digits[:3], phone_digits[3:6], phone_digits[6:]
                )
                record.phone = formatted_phone
