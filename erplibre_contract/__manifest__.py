# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'ERPLibre contract',
    'version': '0.1',
    'author': "TechnoLibre",
    'website': 'https://technolibre.ca',
    'license': 'AGPL-3',
    'category': 'stock',
    'summary': 'INSTALL ERPLibre contract',
    'description': """
ERPLibre contract
==================

""",
    'depends': [
        # Custom ERPLibre
        'erplibre_base',

        # odoo/addons

        # addons/OCA_contract
        'agreement',
        'agreement_account',
        'agreement_legal',
        'agreement_legal_sale',
        #'agreement_legal_sale_fieldservice',
        #'agreement_maintenance',
        #'agreement_mrp',
        'agreement_project',
        #'agreement_repair',
        'agreement_sale',
        'agreement_serviceprofile',
        'agreement_stock',
        'contract',
        'contract_forecast',
        'contract_invoice_start_end_dates',
        'contract_layout_category_hide_detail',
        'contract_mandate',
        'contract_payment_mode',
        'contract_sale',
        'contract_sale_invoicing',
        'contract_sale_mandate',
        'contract_sale_payment_mode',
        'contract_transmit_method',
        'contract_variable_qty_prorated',
        'contract_variable_qty_timesheet',
        'contract_variable_quantity',
        'product_contract',
        'product_contract_variable_quantity',

        # -lien vers contrat-cadre vide ou auto rempli mais non signé dans les notes et conditions
        # - pouvoir Envoyer par courriel les contrats
        #
        # -voir via le portail
        # -downloader le contrat
        # demande de signer à la personne via le lien
        # genere un novueau pdf avec la signature
        # avec interface admin qu'on puisse changer les options dans le contrats'
        # --> champs à remplir pour cahque client
        # --> options de contrats au nvieau de la PI
        #
        # CRM --> NDA --> génération du contrat temp non signé  --> soumissions--> accepté -->
        # envoi par email/et/ou affichage et demande de signature à l'écran--> signature en ligne
        # --> création PDF (comment on assure l'aspect non modifiable du contrat? on hash le document? et on envoi une preuve au client?
        # il nous faudrait un 3rd party --> https://manpages.ubuntu.com/manpages/bionic/man1/sha3sum.1p.html --> (clef GPG https://www.gnupg.org/gph/en/manual/c14.html)
        # --> soumission est validée

    ],
    'data': [],
    'installable': True,
}
