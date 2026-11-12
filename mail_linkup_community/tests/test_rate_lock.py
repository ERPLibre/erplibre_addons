# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""The lock of the keys of a limit (LU-NF-006): two transactions that count
and add the events of one key run one after the other, through two
database cursors.

The second transaction takes its snapshot before the first commits; once
the first commits, its lock fails with a serialization error, which the
RPC layer retries (``odoo.service.model.retrying``) with a snapshot that
holds the events of the first. The row of the key lives in a committed
transaction and is removed once the test ends.
"""

import psycopg2
from odoo import SUPERUSER_ID, api
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import SQL, mute_logger
from odoo.tools.sql import table_exists

from .. import uninstall_hook
from ..models.linkup_rate_event import LOCK_TABLE

KIND = "verification"
VALUE = "linkup-rate-lock-test"


@tagged("post_install", "-at_install")
class TestLinkupRateLock(TransactionCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self._remove_committed_lock)

    def _remove_committed_lock(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            key = f"{KIND}:{env['linkup.rate.event']._linkup_key(VALUE)}"
            cr.execute(
                SQL(
                    "DELETE FROM %s WHERE key_hash = %s",
                    SQL.identifier(LOCK_TABLE),
                    key,
                )
            )

    def test_concurrent_lock_fails_to_serialize(self):
        """A transaction whose snapshot predates the commit of another lock
        of the key fails to lock it."""
        with self.registry.cursor() as late:
            late.execute("SELECT 1")
            with self.registry.cursor() as first:
                env = api.Environment(first, SUPERUSER_ID, {})
                env["linkup.rate.event"]._linkup_lock(KIND, [VALUE])
            env = api.Environment(late, SUPERUSER_ID, {})
            with (
                self.assertRaises(psycopg2.errors.SerializationFailure),
                mute_logger("odoo.sql_db"),
            ):
                env["linkup.rate.event"]._linkup_lock(KIND, [VALUE])
            late.rollback()


@tagged("post_install", "-at_install")
class TestLinkupRateLockUninstall(TransactionCase):
    """Without the cleanup of a committed row: the drop holds its lock
    until the test transaction rolls back."""

    def test_uninstall_drops_the_lock_table(self):
        """The uninstallation drops the table of the locks, which the ORM
        does not remove; the test transaction rolls the drop back."""
        self.env["linkup.rate.event"]._linkup_lock(KIND, [VALUE])
        self.assertTrue(table_exists(self.env.cr, LOCK_TABLE))
        uninstall_hook(self.env)
        self.assertFalse(table_exists(self.env.cr, LOCK_TABLE))
