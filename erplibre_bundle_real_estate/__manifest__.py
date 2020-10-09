# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre real_estate',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'real_estate',
    'summary': 'INSTALL ERPLibre real_estate',
    'description': """
ERPLibre real_estate
=============================

""",
    'depends': [
        # addons/ERPLibre_erplibre_addons
        'erplibre_base',
        'erplibre_base_quebec',
        'erplibre_crm',
        'erplibre_e-commerce',
        'erplibre_helpdesk',
        'erplibre_hr',
        'erplibre_partner',
        'erplibre_property_management',
        #'erplibre_property_management_2',
        'erplibre_sale',
        'erplibre_stock',
        'erplibre_website',

    ],
    'data': [],
    'installable': True,
}
