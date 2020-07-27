# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre helpdesk',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'helpdesk',
    'summary': 'INSTALL ERPLibre helpdesk',
    'description': """
ERPLibre helpdesk
==================

""",
    'depends': [
        # Custom ERPLibre
        'erplibre_base',

        'helpdesk_mailing_list',
        'helpdesk_join_team',
        'helpdesk_mailing_list',
        'helpdesk_mgmt',
        'helpdesk_mgmt_project',
        'helpdesk_motive',
        'helpdesk_mrp',
        'helpdesk_partner',
        'helpdesk_service_call',
        'helpdesk_supplier',
        'helpdesk_type',











    ],
    'data': [],
    'installable': True,
}
