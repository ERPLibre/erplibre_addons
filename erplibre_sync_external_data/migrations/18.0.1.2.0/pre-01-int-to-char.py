from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    table = "table_name"
    if not openupgrade.table_exists(env.cr, table):
        return

    openupgrade.rename_columns(
        env.cr,
        {
            table: [
                # renomme projet_numero -> projet_numero__legacy (nom versionné)
                (
                    "projet_numero",
                    openupgrade.get_legacy_name("projet_numero"),
                ),
            ],
        },
    )
