======================
ERPLibre Odoo CLI base
======================

Command line commands for ``odoo-bin``, kept out of the Odoo core.

The module is never installed (``installable: False``): it only carries a
``cli/`` package. ``odoo-bin`` imports the ``cli/`` package of every module
of the addons path before running a command, and a command class registered
later replaces an earlier one of the same name.

Commands
========

``db``
    Odoo's ``db`` command (load, dump, duplicate, rename, drop) extended with:

    * ``db create [-f] [--demo] [--lang fr_CA] [--login admin]
      [--password admin] [--phone N] [--country ca] DB``
    * ``db list``: one database name per line on stdout, no log line;
    * ``db list-incompatible``: the databases of another Odoo version;
    * ``db version``: the Odoo version;
    * ``db drop [--if-exists] DB``: checks the master password, read from
      the ``MASTER_PWD`` environment variable (``admin`` when unset), before
      anything else; an absent database is an error unless ``--if-exists``;
    * ``-f`` on ``create``, ``load``, ``duplicate`` and ``rename`` checks the
      same master password before it deletes an existing database;
    * ``--image NAME`` on ``load`` and ``dump``: ``./image_db/NAME.zip``, or
      a path when the value contains ``/`` (``.zip`` appended when missing);
    * ``--move`` on ``load``: restores as a moved database, which keeps the
      UUID of the dump; without it, Odoo 16.0's ``load`` restores a copy,
      with a new UUID.

    Global options (``-c``, ``--db_host``...) come before the subcommand, as
    with Odoo: ``db -c FILE list``.

``i18n -d DB --module NAME --addons_path OUTPUT [--lang fr_CA]``
    Writes ``OUTPUT/NAME/i18n/NAME.pot`` and ``OUTPUT/NAME/i18n/LANG.po``
    for an installed module.

``module uninstall [-c FILE] -d DB a,b``
    Uninstalls the installed modules of the list and every installed module
    that depends on them. The modules are marked ``to remove`` and the
    registry is reloaded, as the server's loading does: a server running
    scheduled actions on the same database does not block the command.

``theme apply [-c FILE] -d DB THEME``
    Installs the theme (and website) when needed, then does what the website
    "Choose theme" button does on the current website, minus the redirection
    to the website editor, which needs an HTTP request. A theme the database
    does not list yet is found after refreshing the module list.

Discovery
=========

The commands are found only when this module's directory is in the addons
path known when ``odoo-bin`` starts: the configuration file of ``ODOO_RC``
(else ``~/.odoorc``), or a leading ``--addons-path=...`` written before the
command name. A ``-c FILE`` written after the command name comes too late
for the discovery. ERPLibre's ``./odoo_bin.sh`` exports ``ODOO_RC``.

The commands extend OCB's ``db`` command. Next to an ERPLibre fork that still
carries the old flag-based ``db`` (no ``Db._check_target``), the module
registers no command: the fork's own ``db`` and ``i18n`` stay, and
``./odoo_bin.sh`` translates the new syntax for them.

Exit codes: 0 success, 1 operational failure (message on stderr), 2 usage
error.
