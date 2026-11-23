The editor is shown to the members of *Administration / Settings*, in
developer mode; the server checks both on every call.

This module does not depend on *code_generator*: it installs on any
database, and the server needs no `--dev` option.

Writing a project as a module is the part of *ERPLibre studio generate*
(`erplibre_studio_generate`), which installs by itself once both this
module and *code_generator* are installed. Install it on a development
database only: *code_generator* installs only on a server started with
`--dev`, and its installation drops the database constraint that keeps
the names of custom fields starting with `x_`. Without it, the project
form says so where the generation buttons would be.

Timeline views are edited once *web_timeline* (OCA/web) is installed:
the studio reads the view types of the database and offers *timeline*
only when that module adds it; this module does not depend on it.

The real preview of a model not created yet, once approved, creates the
model inside a savepoint of the database and rolls it back: while it
renders, the writers of the users table and of the tables the new models
point to wait, at most its lock timeout (2 s) per lock and its statement
timeout (15 s) per statement. One real preview runs at a time in a
process. On a threaded server (`--workers 0`), the other requests of the
process share its registry and may see the temporary model for that
time; with workers, each one has its own. The simulation, the default,
writes nothing.

A properties field a project creates is a custom field whose definition
(its many2one, and the properties definition field of the comodel) is
kept in the column `erplibre_studio_properties_definition` this module
adds to the fields: Odoo alone builds a custom properties field without
a definition, and every form of its model would fail to read it. A row
whose definition does not resolve is left out of the registry, with a
warning in the log. Uninstalling this module is refused while a project
has fields in the database: revert it first, or install its generated
module.
