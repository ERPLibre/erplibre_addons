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
report. Each line still shows the current state of its module, so that a
module installed since no longer offers to install it.
