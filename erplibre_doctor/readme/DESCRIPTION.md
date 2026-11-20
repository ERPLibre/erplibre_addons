The ERPLibre doctor analyses the database against what the ERPLibre
checkout suggests and keeps each analysis as a report.

Its first check reads `conf/module_list_image_db_odoo.json` in the
checkout: the image `odoo<series>_base` (`odoo18.0_base` on Odoo 18.0)
lists the modules every ERPLibre database of the series starts with. The
report gives one line per suggested module with its state in the
database; a module that is not installed, or that the module list does
not know, is a problem.

The modules found not installed can be installed from the report: they
are marked « to install » with their dependencies, and a confirmation
lists every scheduled module change before anything is installed. Confirm
installs them and reloads the page; Cancel takes the marks back. A
confirmation closed otherwise leaves the marks, and the report still
offers to finish the install.

A report is a snapshot: it never runs again, a new analysis makes a new
report, named « DOCTOR/<year>/<month>/<day>/<n> » with `n` counting
from 1 each day. Each line still shows the current state of its module,
so that a module installed since no longer offers to install it.

The scheduled action *ERPLibre: doctor* runs an analysis every day. When
it finds a problem, or cannot complete, it posts a message on its report
to the internal users chosen in the settings: each receives it in the
Odoo inbox or by e-mail, as their notification preference says. The
message lists the modules in problem; the recipients who are not
administrators can read the reports, the analyses and the installs stay
with *Administration / Settings*.
