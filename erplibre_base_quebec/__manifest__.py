# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre base Quebec',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'Base',
    'summary': 'INSTALL ERPLibre base Quebec',
    'description': """
ERPLibre base Quebec
=====================

""",
    'depends': [
        # Custom ERPLibre
        #'erplibre_base',
        'configure_quebec_tax',
        'partner_no_vat',

        # Canada
        'l10n_ca',

    ],
    'data': [],
    'installable': True,
}
