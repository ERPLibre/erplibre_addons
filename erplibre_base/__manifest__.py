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

        # Muk
        'muk_web_theme',
        'muk_utils',
        'muk_branding',
        'muk_mail_branding',
        'muk_web_branding',
        'muk_web_theme_mail',
        'muk_web_utils',

        # Server-tools
        'fetchmail_notify_error_to_sender',

        # Social
        'mail_debrand',

        # Partner
        'partner_quebec_tz',

    ],
    'data': [],
    'installable': True,
}
