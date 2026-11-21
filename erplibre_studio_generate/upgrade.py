# © 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""The upgrade of the projects generated with erplibre_studio_generate
18.0.1.1.0. The post-migration of erplibre_studio, which runs first,
rewrites what an applied project applied in the current form of the
snapshot; the snapshot of the last generation keeps the former form and
no longer matches. A project still « generated » held the same draft in
both: its generation snapshot takes the rewritten one. Run from the
post-migration of 18.0.1.2.0; a second run changes nothing."""

PROJECT_TABLE = "erplibre_studio_project"


def migrate_generated(env):
    cr = env.cr
    cr.execute(
        f"SELECT id FROM {PROJECT_TABLE} WHERE state = 'generated' "
        "AND applied_snapshot IS NOT NULL "
        "AND generated_snapshot IS DISTINCT FROM applied_snapshot"
    )
    ids = [row[0] for row in cr.fetchall()]
    for project in env["erplibre.studio.project"].browse(ids):
        project._internal().write({"generated_snapshot": project.applied_snapshot})
        project._update_state()
