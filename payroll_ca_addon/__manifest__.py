# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Canada Payroll',
    'category': 'Human Resources',
    'author': 'Alexandre Ferreira Benevides (TechnoLibre)',
    'depends': ['hr_payroll', 'l10n_ca'],
    'description': """
French Payroll Rules.
=====================

    - Configuration of hr_payroll for Canada localization
    - All main contributions rules for Canadian payslip
    - New payslip report

TODO:
-----
    - Integration with holidays module for deduction and allowance
    - Integration with hr_payroll_account for the automatic account_move_line
      creation from the payslip
    - Remake the report under webkit
    - The payslip.line with appears_in_payslip = False should appears in the
      payslip interface, but not in the payslip report
    """,
    'data': [
        'data/l10n_CA_hr_payroll_data.xml',
        'views/l10n_CA_hr_payroll_view.xml',
        'views/res_config_settings_views.xml',
        'report/report_l10n_CA_fiche_paye.xml',
        'report/l10n_CA_hr_payroll_report.xml',
    ],
}
