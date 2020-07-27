# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre crm',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'crm',
    'summary': 'INSTALL ERPLibre crm',
    'description': """
ERPLibre crm
=============

""",
    'depends': [
        # Custom ERPLibre
        'erplibre_base',

        'crm_filter_all',

        #odoo/addons
        'crm',
        'crm_livechat',
        'crm_phone_validation',
        'crm_project',
        'crm_reveal',




    ],
    'data': [],
    'installable': True,
}
