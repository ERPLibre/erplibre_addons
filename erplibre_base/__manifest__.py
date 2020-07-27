# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre base',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'Base',
    'summary': 'INSTALL ERPLibre base',
    'description': """
ERPLibre base
===============

""",
    'depends': [
        # Custom ERPLibre
        # OCA
        'web_responsive',

        # OCA server-brand
        'disable_odoo_online',
        'remove_odoo_enterprise',

        # OCA website
        'website_odoo_debranding',
        'website_no_crawler',

        # Muk
        'muk_web_theme',
        'muk_utils',
        'muk_branding',
        'muk_hr_utils',
        'muk_mail_branding',
        'muk_web_branding',
        'muk_web_theme_mail',
        'muk_web_utils',
        'muk_website_branding',

        # Server-tools
        'fetchmail_notify_error_to_sender',

        # Social
        'mail_debrand',

        # Partner
        'partner_quebec_tz',

        # addons/Smile-SA_odoo_addons
        'Smile-SA_odoo_addons',

    ],
    'data': [],
    'installable': True,
}
