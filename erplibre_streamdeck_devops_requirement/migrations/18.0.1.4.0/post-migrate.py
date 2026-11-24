# Copyright 2026 TechnoLibre inc. - Mathieu Benoit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Rewrite, from the data files, the requirements whose text changed in
this version, and the proofs whose test moved to another repository.

The data files are noupdate: an upgrade creates the records it does not
find and leaves the others as they are, so a requirement rewritten since
would keep its former text, and a proof its former reference. The
records listed in REWRITTEN, and the proofs that cite a repository of
MOVED, are loaded again from their file, a hand edit of them included;
every other record keeps its own. Their translations are dropped but for
en_US, so that the loading of the catalogs that follows this script
fills them from the new texts.
"""

import copy

from lxml import etree

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL
from odoo.tools.convert import xml_import
from odoo.tools.misc import file_path

MODULE = "erplibre_streamdeck_devops_requirement"

# Data file -> XML ids of its records rewritten in this version.
REWRITTEN = {
    "data/requirement_inventory.xml": (
        "test_sd_inv_r24_1",
        "req_sd_inv_r42",
    ),
    "data/requirement_control.xml": (
        "req_sd_ctl_r27",
        "test_sd_ctl_r27_1",
        "req_sd_ctl_r43",
        "req_sd_ctl_r47",
    ),
    "data/requirement_monitoring.xml": ("req_sd_mon_r38",),
}

# Reference prefix -> data files whose proofs citing it are loaded again:
# the tests of the deck program live in their own repository since this
# version, so a proof that names one changed its reference.
MOVED = {
    "erplibre_streamdeck:": (
        "data/devops_requirement_test.xml",
        "data/requirement_control.xml",
    ),
}


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    filenames = list(REWRITTEN)
    filenames += [f for fs in MOVED.values() for f in fs if f not in filenames]
    for filename in filenames:
        xmlids = REWRITTEN.get(filename, ())
        moved = tuple(p for p, files in MOVED.items() if filename in files)
        path = file_path("%s/%s" % (MODULE, filename))
        kept = etree.Element("odoo")
        for record in etree.parse(path).getroot().iter("record"):
            if record.get("id") in xmlids or _cites(record, moved):
                kept.append(copy.deepcopy(record))
        xml_import(
            env, MODULE, {}, "init", noupdate=True, xml_filename=path
        ).parse(kept)
        for record in kept.iter("record"):
            # The reload writes only the fields the file names: a
            # requirement whose file states no gap, done since, would
            # keep its former one.
            if record.get("model") == "devops.requirement" and not (
                record.xpath("field[@name='missing']")
            ):
                env.ref("%s.%s" % (MODULE, record.get("id"))).missing = False
        for record in kept.iter("record"):
            _keep_english_only(env.ref("%s.%s" % (MODULE, record.get("id"))))


def _cites(record, prefixes):
    """True when `record` is a proof whose reference, in the data file,
    starts with one of `prefixes`."""
    if not prefixes or record.get("model") != "devops.requirement.test":
        return False
    reference = record.xpath("string(field[@name='reference'])")
    return reference.startswith(prefixes)


def _keep_english_only(record):
    """Drop the translations of the translated fields of `record`, the
    en_US value kept."""
    record.flush_recordset()
    for name, field in record._fields.items():
        if field.translate is not True or not field.store:
            continue
        record.env.cr.execute(
            SQL(
                "UPDATE %s SET %s = jsonb_build_object('en_US', %s->'en_US')"
                " WHERE id = %s AND %s IS NOT NULL",
                SQL.identifier(record._table),
                SQL.identifier(name),
                SQL.identifier(name),
                record.id,
                SQL.identifier(name),
            )
        )
    record.invalidate_recordset()
