from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    table = "table_name"
    if not openupgrade.table_exists(env.cr, table):
        return

    legacy = openupgrade.get_legacy_name("projet_numero")

    # Copie int -> char (cast explicite)
    env.cr.execute(
        f"""
        UPDATE {table}
           SET numero_projet = {legacy}::text
         WHERE {legacy} IS NOT NULL
           AND (numero_projet IS NULL OR numero_projet = '')
    """
    )

    openupgrade.drop_columns(
        env.cr,
        [
            (table, legacy),
        ],
    )
