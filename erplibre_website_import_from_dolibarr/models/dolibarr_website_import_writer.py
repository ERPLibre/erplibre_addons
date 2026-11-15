# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""All ORM writes of an import run, in a fixed order.

Every record goes through _map_upsert(), which owns the identity table
and the local edit policy. The writer runs with the website, its default
language and its company in context, and never commits.

Media become public attachments served from the website's own origin, so
a media is stored only when its bytes match an allowed type, an SVG is
always sanitised, and a URL that another record or a controller route
already answers is never taken over.
"""

import base64
import dataclasses
import hashlib
import json
import os
import posixpath
import time
import urllib.parse

import werkzeug.exceptions
import werkzeug.routing
from lxml import etree
from odoo import models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.mimetypes import guess_mimetype

from ..dolibarr_site import html2arch, pipeline, urls
from ..dolibarr_site.messages import finding
from ..dolibarr_site.model import CONVERTER_VERSION, SourceError, valid_relpath
from ..dolibarr_site.urls import local_path
from .dolibarr_website_import import BudgetExhausted, UrlUnavailable

MEDIA_MIMETYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".avif": "image/avif", ".ico": "image/x-icon", ".bmp": "image/bmp",
    ".woff": "font/woff", ".woff2": "font/woff2", ".ttf": "font/ttf",
    ".otf": "font/otf", ".eot": "application/vnd.ms-fontobject",
    ".css": "text/css", ".pdf": "application/pdf", ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    ".mp4": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg",
    ".js": "application/javascript",
}  # fmt: skip
META_FIELDS = (
    "website_meta_title",
    "website_meta_description",
    "website_meta_keywords",
    "website_meta_og_img",
)
HASH_FIELDS = {
    "post": (
        "name", "subtitle", "content", *META_FIELDS, "is_published",
        "published_date", "cover_properties", "blog_id", "author_id",
    ),
    "media": ("checksum", "name", "url", "mimetype"),
    "css": ("checksum", "url", "mimetype"),
    "js": ("checksum", "url", "mimetype"),
    "head_view": ("arch_db", "name", "active"),
    "blog_style_view": ("arch_db", "name", "active", "inherit_id"),
    "menu": ("name", "url", "page_id", "new_window", "parent_id"),
    "redirect": ("url_from", "url_to", "redirect_type"),
    "blog": (),
}  # fmt: skip
ERROR_PAGE_REFS = ("404", "500", "501", "503")
MENU_CAP = 200
# Candidates tried for one page URL before the page is given up.
MAX_URL_CANDIDATES = 1000
# Errors of one page or post write; the savepoint around the write undoes
# whatever part of it reached the database.
WRITE_ERRORS = (ValidationError, UserError, ValueError, etree.LxmlError)
# Kinds whose record is a public attachment of the website.
_ATTACHMENT_KINDS = ("media", "css", "js")
# Leading bytes of each binary type of MEDIA_MIMETYPES. RIFF, ftyp and
# EOT need more than a prefix and are recognised in _content_type().
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"\x00\x00\x01\x00", "image/x-icon"),
    (b"wOFF", "font/woff"),
    (b"wOF2", "font/woff2"),
    (b"\x00\x01\x00\x00", "font/ttf"),
    (b"true", "font/ttf"),
    (b"OTTO", "font/otf"),
    (b"%PDF-", "application/pdf"),
    (b"ID3", "audio/mpeg"),
    (b"\x1a\x45\xdf\xa3", "video/webm"),
)
_AVIF_BRANDS = (b"avif", b"avis")
# Extensions whose bytes are text: their type cannot be read from the
# content, only refused when the content is markup.
_TEXT_EXTS = (".css", ".js", ".svg")


def _family(mimetype):
    """Coarse kind of a media type; two types of one family may swap."""
    if mimetype == "image/svg+xml":
        return "svg"
    major = mimetype.split("/")[0]
    if major in ("audio", "video"):
        return "av"
    if major == "font" or mimetype == "application/vnd.ms-fontobject":
        return "font"
    return major if major == "image" else mimetype


def _content_type(data, ext):
    """Media type that the leading bytes of a binary file prove, or None.

    The extension only settles what the bytes cannot: an Ogg stream is
    audio or video, and so is an ISO media file other than AVIF.
    """
    for magic, mimetype in _MAGIC:
        if data.startswith(magic):
            return mimetype
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    if data[:4] == b"OggS":
        return "video/ogg" if ext == ".ogv" else "audio/ogg"
    if data[4:8] == b"ftyp":
        if data[8:12] in _AVIF_BRANDS:
            return "image/avif"
        return "audio/mp4" if ext == ".m4a" else "video/mp4"
    if len(data) > 36 and data[34:36] == b"LP":
        return "application/vnd.ms-fontobject"
    if len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0:
        return "audio/mpeg"
    return None


def _is_markup(data):
    """True when Odoo, or a first non-blank "<", reads the bytes as markup.

    A public attachment of that kind would be HTML or XML on the site's
    origin whatever type the import stores for it.
    """
    guessed = (guess_mimetype(data) or "").lower()
    if "html" in guessed or "xml" in guessed or "svg" in guessed:
        return True
    return data.lstrip(b"\xef\xbb\xbf \t\r\n\f").startswith(b"<")


class WriterResolver:
    """Resolver of engine tokens backed by the records of this import.

    It follows the protocol of html2arch.DictResolver: page_url(ref) and
    media_url(relpath) return a site path or None, blog_id() and
    website_id() return integers. A site-level name such as
    htmlheader.html is never a key of records, so it resolves to None.
    """

    def __init__(self, records, media, blog, website):
        self.records = records
        self.media = media
        self.blog = blog
        self.website = website

    def page_url(self, ref):
        record = self.records.get(ref)
        if not record:
            return None
        if record._name == "website.page":
            return record.url
        return record.website_url

    def media_url(self, relpath):
        return self.media.get(relpath)

    def blog_id(self):
        return self.blog.id

    def website_id(self):
        return self.website.id


class DolibarrWebsiteImport(models.Model):
    _inherit = "dolibarr.website.import"

    def _writer(self):
        """This run in the writer's context, after the group gate."""
        self._check_import_access()
        website = self.website_id
        return self.with_context(
            website_id=website.id,
            lang=website.default_lang_id.code or "en_US",
            allowed_company_ids=[website.company_id.id],
            dolibarr_website_import=True,
            mail_create_nolog=True,
            mail_create_nosubscribe=True,
            tracking_disable=True,
        )

    def _check_budget(self, deadline, wrote=True):
        """BudgetExhausted once deadline has passed and the pass has
        written a record: every pass, so every batch, makes progress."""
        if deadline is not None and time.monotonic() > deadline and wrote:
            raise BudgetExhausted()

    def _hash(self, values):
        payload = json.dumps(values, sort_keys=True, default=str)
        return hashlib.sha256(
            (payload + CONVERTER_VERSION).encode("utf-8")
        ).hexdigest()

    def _record_values(self, kind, record):
        if kind == "page":
            view = record.view_id
            values = {"arch_db": view.arch_db, "name": view.name}
            values.update({name: view[name] for name in META_FIELDS})
            values.update(
                is_published=record.is_published,
                website_indexed=record.website_indexed,
            )
            return values
        values = {}
        for name in HASH_FIELDS[kind]:
            value = record[name]
            if isinstance(value, models.BaseModel):
                # A parent view counts by its key: copy-on-write moves a
                # child view under a copy of its parent with the same key.
                value = value.key if name == "inherit_id" else value.id
            values[name] = value
        return values

    def _record_hash(self, kind, record):
        """Hash of the tracked fields as stored in the database now."""
        self.env.flush_all()
        record.invalidate_recordset()
        if kind == "page":
            record.view_id.invalidate_recordset()
        return self._hash(self._record_values(kind, record))

    def _map_line(self, kind, ref):
        return self.env["dolibarr.website.import.map"].search(
            [
                ("website_id", "=", self.website_id.id),
                ("source_key", "=", self.source_key),
                ("kind", "=", kind),
                ("ref", "=", ref),
            ],
            limit=1,
        )

    def _is_current(self, kind, ref, model, content_hash):
        """True when _map_upsert would write nothing: the record exists
        and its line already holds content_hash. A resumed batch passes
        such records without counting them as progress."""
        line = self._map_line(kind, ref)
        return bool(
            line
            and line.content_hash == content_hash
            and self._line_record(kind, line, model)
        )

    def _map_create(self, kind, ref, record, content_hash, action):
        return self.env["dolibarr.website.import.map"].create(
            {
                "website_id": self.website_id.id,
                "source_key": self.source_key,
                "kind": kind,
                "ref": ref,
                "res_model": record._name,
                "res_id": record.id,
                "content_hash": content_hash,
                "written_hash": self._record_hash(kind, record),
                "last_import_id": self.id,
                "last_action": action,
            }
        )

    def _this_run_action(self, line, default):
        """created/recreated earlier in this run stays the run's action."""
        if line.last_import_id.id == self.id and line.last_action in (
            "created",
            "recreated",
        ):
            return line.last_action
        return default

    def _line_record(self, kind, line, model):
        """Record of a map line, or an empty recordset of model.

        A line counts as missing when it names another model, a deleted
        record, or a record of another website: a post through its blog,
        any other kind through its own website_id. An attachment (media,
        css, js) also needs res_model ir.ui.view, the mark of a public
        media, so the import never writes an attachment that belongs to
        another record or website.
        """
        Model = self.env[model]
        if not line or line.res_model != model:
            return Model
        record = Model.browse(line.res_id).exists()
        if not record:
            return Model
        website = (
            record.blog_id.website_id if kind == "post" else record.website_id
        )
        if website != self.website_id:
            return Model
        if kind in _ATTACHMENT_KINDS and record.res_model != "ir.ui.view":
            return Model
        return record

    def _record_finding(self, code, kind, ref, record):
        """One report line naming a record of the identity table."""
        self._add_line(
            finding(
                code,
                page_ref=ref if kind in ("page", "post") else "",
                kind=kind,
                ref=ref,
            ),
            record,
        )

    def _map_upsert(
        self,
        kind,
        ref,
        model,
        vals,
        content_hash,
        create_vals=None,
        finder=None,
        write=None,
    ):
        """Create, update or keep one record; return (record, action).

        No line: create. Line to a missing record: look it up with finder
        (a view moved by copy-on-write), else create again with recreated.
        A found record only takes the line's res_id: it keeps the line's
        content and written hashes, so an edit made before or after the
        move is still told apart from the import's own write, and it gets
        the action of the hash comparison below, never recreated. Same
        content hash: nothing is written. Changed hash:
        written when the record still reads as the import left it;
        otherwise kept with local_edit_kept, or overwritten with
        overwrite_local_edits.
        The record and its map line are written together, so a stop
        between two calls never leaves a record outside the table.
        """
        line = self._map_line(kind, ref)
        Model = self.env[model]
        record = self._line_record(kind, line, model)
        if not line:
            record = Model.create(dict(vals, **(create_vals or {})))
            self._map_create(kind, ref, record, content_hash, "created")
            return record, "created"
        if not record:
            record = finder() if finder else Model
            if record:
                line.write({"res_model": record._name, "res_id": record.id})
            else:
                record = Model.create(dict(vals, **(create_vals or {})))
                line.write(
                    {
                        "res_model": record._name,
                        "res_id": record.id,
                        "content_hash": content_hash,
                        "written_hash": self._record_hash(kind, record),
                        "last_import_id": self.id,
                        "last_action": "recreated",
                    }
                )
                self._record_finding("recreated", kind, ref, record)
                return record, "recreated"
        if line.content_hash == content_hash:
            action = self._this_run_action(line, "unchanged")
            line.write({"last_import_id": self.id, "last_action": action})
            return record, action
        edited = self._record_hash(kind, record) != line.written_hash
        if edited and not self.overwrite_local_edits:
            line.write(
                {"last_import_id": self.id, "last_action": "kept_local"}
            )
            self._record_finding("local_edit_kept", kind, ref, record)
            return record, "kept_local"
        if write:
            write(record, vals)
        else:
            record.write(vals)
        action = self._this_run_action(line, "updated")
        line.write(
            {
                "content_hash": content_hash,
                "written_hash": self._record_hash(kind, record),
                "last_import_id": self.id,
                "last_action": action,
            }
        )
        if edited:
            self._record_finding("local_edit_overwritten", kind, ref, record)
        return record, action

    def _ensure_blog(self):
        """One blog.blog per (website, key), created once, never renamed."""
        record, _action = self._map_upsert(
            "blog",
            "",
            "blog.blog",
            {
                "name": self.blog_name or "Blog",
                "website_id": self.website_id.id,
            },
            self._hash({}),
            write=lambda rec, vals: None,
        )
        return record

    # Media

    def _media_type(self, media, data):
        """(mimetype, data) to store for one media, or None to skip it.

        The extension names the expected type; the bytes must prove a
        type of the same family, and that proven type is the one stored.
        Text types are refused when the bytes are markup; an SVG goes
        through html2arch.sanitize_svg and must keep an svg root.
        """
        ext = os.path.splitext(media.relpath)[1].lower()
        expected = MEDIA_MIMETYPES.get(ext)
        if not expected:
            return None
        if ext == ".svg":
            return self._sanitised_svg(media, data)
        if not data or _is_markup(data):
            return None
        if ext in _TEXT_EXTS:
            return expected, data
        proven = _content_type(data, ext)
        if proven not in MEDIA_MIMETYPES.values():
            return None
        if _family(proven) != _family(expected):
            return None
        return proven, data

    def _sanitised_svg(self, media, data):
        try:
            clean, removed = html2arch.sanitize_svg(data)
        except ValueError:
            return None
        if removed:
            self._add_line(
                finding(
                    "svg_sanitised",
                    relpath=media.relpath,
                    removed=", ".join(removed),
                )
            )
        return "image/svg+xml", clean

    def _is_script(self, media):
        return os.path.splitext(media.relpath)[1].lower() == ".js"

    def _read_media(self, source, media, url):
        """Bytes of one zip member, or None with a media_unreadable line.

        An unreadable member (corrupt deflate stream, CRC error) skips
        that file only; the rest of the zip is still imported.
        """
        try:
            return source.read_media(media)
        except SourceError as exc:
            self._add_line(
                finding("media_unreadable", url=url, error=str(exc))
            )
            return None

    def _url_taken(self, url, own_id=0):
        """True when url already serves something other than own_id.

        A website attachment at that url, a website.page at that path
        whatever its case, or a controller route: each one is served
        before, or instead of, an attachment of this import.
        """
        website = self.website_id
        domain = [("website_id", "in", (website.id, False))]
        taken = (
            self.env["ir.attachment"]
            .sudo()
            .search_count(
                domain + [("url", "=", url), ("id", "!=", own_id)], limit=1
            )
        )
        return bool(taken) or self._page_at(url) or self._is_route(url)

    def _write_media(self, site, source, deadline=None):
        """Media attachments; returns relpath -> served URL.

        The budget is checked before each media, never between a record
        and its map line, and only once the pass has written a media.
        """
        website = self.website_id
        found = {}
        wrote = False
        writer = self.with_context(image_no_postprocess=True)
        for count, media in enumerate(site.media):
            self._check_budget(deadline, wrote)
            if self.max_media and count >= self.max_media:
                self._add_line(
                    finding(
                        "media_capped", limit="max_media %d" % self.max_media
                    )
                )
                break
            if not valid_relpath(media.relpath, site.source_key):
                self._add_line(
                    finding("media_name_refused", relpath=media.relpath)
                )
                continue
            if self._is_script(media) and not self.keep_scripts:
                self._add_line(
                    finding(
                        "script_removed",
                        ref=media.relpath,
                        what="script file",
                    )
                )
                continue
            url = "/medias/" + media.relpath
            data = self._read_media(source, media, url)
            if data is None:
                continue
            typed = self._media_type(media, data)
            if not typed:
                self._add_line(
                    finding("media_skipped_type", relpath=media.relpath)
                )
                continue
            mimetype, data = typed
            name = posixpath.basename(media.relpath)
            line = self._map_line("media", media.relpath)
            taken = self._url_taken(
                url, self._line_record("media", line, "ir.attachment").id or 0
            )
            vals = {
                "name": name,
                "datas": base64.b64encode(data),
                "mimetype": mimetype,
                "public": True,
                "type": "binary",
                "website_id": website.id,
                "res_model": "ir.ui.view",
                "res_id": 0,
            }
            if not taken:
                vals["url"] = url
            digest = self._hash(
                {
                    "checksum": hashlib.sha1(data).hexdigest(),
                    "name": name,
                    "url": url if not taken else "conflict:" + url,
                    "mimetype": mimetype,
                }
            )
            current = self._is_current(
                "media", media.relpath, "ir.attachment", digest
            )
            record, action = writer._map_upsert(
                "media", media.relpath, "ir.attachment", vals, digest
            )
            wrote = wrote or (not current and action != "kept_local")
            # A kept local edit is left as it is, url and written hash
            # included, so the next run reports it again.
            if (
                taken
                and action != "kept_local"
                and not (record.url or "").startswith("/web/content/")
            ):
                record.url = "/web/content/%d/%s" % (
                    record.id,
                    urllib.parse.quote(name),
                )
                self._map_line("media", media.relpath).written_hash = (
                    self._record_hash("media", record)
                )
                self._add_line(
                    finding(
                        "media_url_conflict", url=url, fallback=record.url
                    ),
                    record,
                )
            if self._is_script(media):
                self._add_line(
                    finding("script_kept", ref=media.relpath, what=url),
                    record,
                )
            found[media.relpath] = record.url
        return found

    # Pages and posts

    def _is_route(self, path):
        """True when a controller route answers path before any page.

        Only the matcher's own "no match" answers are read: NotFound is
        no route; a method or redirect answer means a route exists. Any
        other error (a routing map that cannot be built) propagates and
        fails the run, never reading as "route exists" for every path.
        """
        try:
            self.env["ir.http"].routing_map().bind("").match(
                path, method="GET"
            )
        except werkzeug.exceptions.NotFound:
            return False
        except (
            werkzeug.exceptions.MethodNotAllowed,
            werkzeug.routing.RequestRedirect,
        ):
            return True
        return True

    def _page_at(self, path, own=None):
        """True when a website.page of this website, or a generic one,
        has path as its URL whatever the case; own is not counted.

        Odoo serves the first such page and redirects any other case of
        the path to it, so a second page there is never reached.
        """
        like = (
            path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        return bool(
            self.env["website.page"]
            .with_context(active_test=False)
            .sudo()
            .search_count(
                [
                    ("website_id", "in", (self.website_id.id, False)),
                    ("url", "=ilike", like),
                    ("id", "!=", own.id if own else 0),
                ],
                limit=1,
            )
        )

    def _path_taken(self, path, own=None):
        """True when a page, an attachment or a route owns path."""
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .search_count(
                [
                    ("website_id", "in", (self.website_id.id, False)),
                    ("url", "=", path),
                ],
                limit=1,
            )
        )
        return (
            bool(attachment)
            or self._page_at(path, own)
            or self._is_route(path)
        )

    def _target_url(self, ref, own=None):
        """(url, wanted) for a page ref; wanted is set on a conflict.

        On a conflict the page goes to /<ref>-page, suffixed by -1, -2...
        until no page, attachment or route owns the path: a wider test
        than website.get_unique_path(), which compares the exact case on
        this website's own pages only. UrlUnavailable is raised when
        MAX_URL_CANDIDATES candidates are all taken.
        """
        html2arch.view_key(self.source_key, ref)
        path = "/" + ref
        if not self._path_taken(path, own):
            return path, None
        base = path + "-page"
        candidate, count = base, 0
        while self._path_taken(candidate, own):
            count += 1
            if count > MAX_URL_CANDIDATES:
                raise UrlUnavailable(
                    self.env._(
                        "No free URL for page %(ref)s after %(count)s"
                        " candidates.",
                        ref=ref,
                        count=MAX_URL_CANDIDATES,
                    )
                )
            candidate = "%s-%d" % (base, count)
        return candidate, path

    def _shell_arch(self, key):
        view = etree.Element("t", {"t-name": key})
        layout = etree.SubElement(view, "t", {"t-call": "website.layout"})
        etree.SubElement(
            layout, "div", {"id": "wrap", "class": "oe_structure"}
        )
        return etree.tostring(view, encoding="unicode")

    def _ensure_record(self, kind, ref, model, create):
        """Existing record of the identity table, or a new shell.

        A shell's map line gets an empty content hash, so the content
        pass always writes it, and that pass reports the created or
        recreated action of this run.
        """
        line = self._map_line(kind, ref)
        record = self._line_record(kind, line, model)
        if record:
            return record
        record = create()
        if line:
            line.write(
                {
                    "res_model": record._name,
                    "res_id": record.id,
                    "content_hash": "",
                    "written_hash": self._record_hash(kind, record),
                    "last_import_id": self.id,
                    "last_action": "recreated",
                }
            )
            self._record_finding("recreated", kind, ref, record)
        else:
            self._map_create(kind, ref, record, "", "created")
        return record

    def _ensure_page_records(self, site, blog):
        """Find or create each website.page and blog.post; URLs are final.

        Only pages with the import status get a record: a layout or
        content container is inlined where it is included, and a ref that
        only site.containers lists is never looked up. A new page or post
        is created unpublished; its content write sets the source's
        publication, so a shell whose content write fails stays hidden.
        """
        website = self.website_id
        records = {}
        for page in site.pages:
            if page.analysis_status != "import":
                continue
            if page.kind == "post":

                def create_post(page=page):
                    return self.env["blog.post"].create(
                        {
                            "name": page.title or page.ref,
                            "blog_id": blog.id,
                            "author_id": website.company_id.partner_id.id,
                            "is_published": False,
                        }
                    )

                records[page.ref] = self._ensure_record(
                    "post", page.ref, "blog.post", create_post
                )
                continue

            def create_page(page=page):
                url, wanted = self._target_url(page.ref)
                if wanted:
                    self._add_line(
                        finding(
                            "url_conflict",
                            page_ref=page.ref,
                            url=url,
                            ref=page.ref,
                            wanted=wanted,
                        )
                    )
                key = html2arch.view_key(site.source_key, page.ref)
                return self.env["website.page"].create(
                    {
                        "name": page.title or page.ref,
                        "type": "qweb",
                        "key": key,
                        "arch": self._shell_arch(key),
                        "url": url,
                        "website_id": website.id,
                        "is_published": False,
                        "website_indexed": page.ref not in ERROR_PAGE_REFS,
                    }
                )

            try:
                records[page.ref] = self._ensure_record(
                    "page", page.ref, "website.page", create_page
                )
            except UrlUnavailable as exc:
                self._add_line(
                    finding(
                        "page_error",
                        page_ref=page.ref,
                        ref=page.ref,
                        reason=str(exc)[:200],
                    )
                )
        return records

    def _company_values(self):
        """Values frozen into blog posts: the website's company, never
        the current user's."""
        company = self.website_id.company_id.sudo()
        partner = company.partner_id
        return {
            "name": company.name or "",
            "email": company.email or "",
            "phone": company.phone or "",
            "website": company.website or "",
            "zip": company.zip or "",
            "city": company.city or "",
            "street": company.street or "",
            "address": partner._display_address(without_company=True) or "",
            "map_url": partner.google_map_link(13) or "",
        }

    # Site assets and views

    def _view_by_key(self, key):
        """The view of this website with key, archived ones included."""
        return (
            self.env["ir.ui.view"]
            .with_context(active_test=False)
            .search(
                [("key", "=", key), ("website_id", "=", self.website_id.id)],
                limit=1,
            )
        )

    def _asset(self, kind, name, text, url, mimetype):
        """Public attachment of the website served at url; kind is its
        identity table kind and name its fixed ref."""
        data = text.encode("utf-8")
        vals = {
            "name": name,
            "datas": base64.b64encode(data),
            "mimetype": mimetype,
            "public": True,
            "type": "binary",
            "website_id": self.website_id.id,
            "res_model": "ir.ui.view",
            "res_id": 0,
            "url": url,
        }
        digest = self._hash(
            {
                "checksum": hashlib.sha1(data).hexdigest(),
                "url": url,
                "mimetype": mimetype,
            }
        )
        return self._map_upsert(kind, name, "ir.attachment", vals, digest)[0]

    def _fallback_head_arch(self, site):
        """Head view arch used when the engine could not render the head:
        the stylesheet only, so every page that calls the view renders."""
        view = etree.Element(
            "t", {"t-name": html2arch.head_key(site.source_key)}
        )
        css = pipeline.css_url(site)
        if css and local_path(css):
            etree.SubElement(view, "link", {"rel": "stylesheet", "href": css})
        return etree.tostring(view, encoding="unicode")

    def _write_site_assets(self, site, rendered):
        """Site CSS and JS attachments, then the standalone head view.

        The JS attachment exists only with keep_scripts; without it the
        site script leaves a script_removed line and nothing else. The
        head arch is stored exactly as the engine produced it.
        """
        key = site.source_key
        if rendered.site_css.strip():
            self._asset(
                "css",
                "styles.css",
                rendered.site_css,
                "/dolibarr-import/%s/styles.css" % key,
                "text/css",
            )
        js = pipeline.js_url(site)
        if rendered.site_js.strip() and js:
            if self.keep_scripts:
                record = self._asset(
                    "js",
                    "javascript.js",
                    rendered.site_js,
                    js,
                    "application/javascript",
                )
                self._add_line(
                    finding("script_kept", ref="javascript.js.php", what=js),
                    record,
                )
            else:
                self._add_line(
                    finding(
                        "script_removed",
                        ref="javascript.js.php",
                        what="site JavaScript",
                    )
                )
        head_key = html2arch.head_key(key)
        arch = rendered.head_arch or self._fallback_head_arch(site)
        name = "Dolibarr import %s head" % key
        vals = {
            "name": name,
            "type": "qweb",
            "key": head_key,
            "website_id": self.website_id.id,
            "arch": arch,
        }
        digest = self._hash({"arch_db": arch, "name": name, "active": True})
        self._map_upsert(
            "head_view",
            "head",
            "ir.ui.view",
            vals,
            digest,
            finder=lambda: self._view_by_key(head_key),
        )

    # Pages and posts content

    def _write_one(self, page, kind, model, vals, digest, write=None):
        """_map_upsert of one page or post inside its own savepoint.

        A write error undoes that record's changes only and becomes a
        page_error line; the pass goes on with the next page. Returns
        True when the record was written.
        """
        current = self._is_current(kind, page.ref, model, digest)
        try:
            with self.env.cr.savepoint():
                _record, action = self._map_upsert(
                    kind, page.ref, model, vals, digest, write=write
                )
            return not current and action != "kept_local"
        except WRITE_ERRORS as exc:
            self._add_line(
                finding(
                    "page_error",
                    page_ref=page.ref,
                    ref=page.ref,
                    reason=str(exc)[:200],
                )
            )
            return False

    def _write_pages(self, site, rendered, records, resolver, deadline=None):
        """Rendered arches on the page views, publication on the pages.

        arch, name and website_meta_* go to page.view_id, so the view key
        never changes; is_published and website_indexed go through
        page.write, never with name or url. The og image is kept only as
        a local path, like a post cover. The budget is checked before each
        page, once the pass has written a page.
        """
        wrote = False
        for page in site.pages:
            arch = rendered.pages.get(page.ref)
            if page.analysis_status != "import" or arch is None:
                continue
            if page.ref not in records:
                continue
            self._check_budget(deadline, wrote)
            og = ""
            if page.image_relpath:
                og = local_path(resolver.media_url(page.image_relpath) or "")
            meta = {
                "website_meta_title": page.seo_title or False,
                "website_meta_description": page.description or False,
                "website_meta_keywords": page.keywords or False,
                "website_meta_og_img": og or False,
            }
            name = page.title or page.ref
            view_vals = dict(meta, arch=arch, name=name)
            page_vals = {
                "is_published": page.published,
                "website_indexed": page.ref not in ERROR_PAGE_REFS,
            }
            digest = self._hash(
                dict(meta, arch_db=arch, name=name, **page_vals)
            )

            def write(record, _vals, view_vals=view_vals, page_vals=page_vals):
                record.view_id.write(view_vals)
                record.write(page_vals)

            wrote = (
                self._write_one(
                    page, "page", "website.page", {}, digest, write=write
                )
                or wrote
            )

    def _write_posts(
        self, site, rendered, records, resolver, blog, deadline=None
    ):
        """Frozen content and metadata of each blog.post.

        is_published and published_date go in the same vals, so the post
        keeps its source date; the author is the partner of the website's
        company; the cover image gives cover_properties and the og image.
        """
        partner = self.website_id.company_id.partner_id
        wrote = False
        for page in site.pages:
            content = rendered.posts.get(page.ref)
            if page.analysis_status != "import" or content is None:
                continue
            if page.ref not in records:
                continue
            self._check_budget(deadline, wrote)
            cover = (
                resolver.media_url(page.image_relpath)
                if page.image_relpath
                else None
            )
            cover = local_path(cover or "")
            vals = {
                "name": page.title or page.ref,
                "subtitle": page.description or False,
                "content": content,
                "website_meta_title": page.seo_title or False,
                "website_meta_description": page.description or False,
                "website_meta_keywords": page.keywords or False,
                "website_meta_og_img": cover or False,
                "is_published": page.published,
                "published_date": page.date_creation or False,
                "blog_id": blog.id,
                "author_id": partner.id,
            }
            if cover:
                vals["cover_properties"] = json.dumps(
                    {
                        "background-image": "url('%s')" % cover,
                        "resize_class": (
                            "o_record_has_cover o_half_screen_height"
                        ),
                        "opacity": "0.4",
                    }
                )
            wrote = (
                self._write_one(
                    page, "post", "blog.post", vals, self._hash(vals)
                )
                or wrote
            )

    # Layout and menus

    def _write_layout(self, site, rendered, records):
        """Extension point for the header and footer of imported pages.

        The Odoo header and footer are kept: a footer container gives
        footer_not_imported, and the header gives the menu entries.
        """
        for ref, role in sorted(site.containers.items()):
            if role == "footer":
                self._add_line(finding("footer_not_imported", ref=ref))
        self._write_menus(site, records)

    def _menu_url(self, url):
        """url when a menu may link to it, else None.

        Accepted: a site path starting with a single slash, or an http(s)
        URL with a host; neither may hold whitespace, a control
        character, a quote, an angle bracket or a backslash.
        """
        if not url or not urls.plain_url(url):
            return None
        if url.startswith("/"):
            return url if local_path(url) else None
        try:
            parts = urllib.parse.urlsplit(url)
            host = parts.hostname
        except ValueError:
            return None
        if parts.scheme in ("http", "https") and host:
            return url
        return None

    def _menu_target(self, item, records):
        """(url, page) of a menu entry; url is None when it is unusable.

        A dolibarr-page: token resolves to its record's URL plus the
        token's suffix; page is set for a website.page, so the entry
        follows a later URL change.
        """
        if not item.target.startswith(urls.PAGE):
            return self._menu_url(item.target), None
        ref, suffix = urls.split_token(item.target)
        record = records.get(ref)
        if not record:
            return None, None
        if record._name == "website.page":
            return self._menu_url(record.url + suffix), record
        return self._menu_url(record.website_url + suffix), None

    def _write_menus(self, site, records):
        """Menu entries appended after the website's own entries.

        A top-level entry gets sequence max + 1 + rank at creation only.
        An entry whose URL, compared through _clean_url(), is already in
        the menu outside this import, or was added by this run, is skipped
        with menu_skipped_existing_url and its children take its place;
        with set_homepage a link to the source home page counts as "/".
        A run adds MENU_CAP entries at most. Labels are stored only as
        the plain name of the entry.
        """
        if not self.import_menu or not site.menu:
            return
        website = self.website_id
        root = website.menu_id
        owned = set(
            self.env["dolibarr.website.import.map"]
            .search(
                [
                    ("website_id", "=", website.id),
                    ("source_key", "=", self.source_key),
                    ("kind", "=", "menu"),
                ]
            )
            .mapped("res_id")
        )
        existing = {}
        for menu in self.env["website.menu"].search(
            [("id", "child_of", root.id), ("id", "!=", root.id)]
        ):
            if menu.id not in owned:
                existing.setdefault(menu._clean_url(), menu)
        added = {}
        state = {"count": 0, "capped": False}
        home = urls.PAGE + site.home_ref if site.home_ref else None

        def place(items, parent, parent_ref, position):
            for item in items:
                url, page = self._menu_target(item, records)
                compare = (
                    "/" if self.set_homepage and item.target == home else url
                )
                other = (
                    (existing.get(compare) or added.get(compare))
                    if url
                    else None
                )
                if url is None or other:
                    if other:
                        self._add_line(
                            finding(
                                "menu_skipped_existing_url",
                                label=item.label,
                                url=compare,
                                existing=other.name,
                            )
                        )
                    position = place(
                        item.children, parent, parent_ref, position
                    )
                    continue
                if state["count"] >= MENU_CAP:
                    if not state["capped"]:
                        state["capped"] = True
                        self._add_line(finding("menu_capped", limit=MENU_CAP))
                    return position
                vals = {
                    "name": item.label,
                    "url": url,
                    "page_id": page.id if page else False,
                    "new_window": item.new_window,
                    "parent_id": parent.id,
                    "website_id": website.id,
                }
                digest = self._hash(
                    {
                        name: vals[name]
                        for name in (
                            "name",
                            "url",
                            "page_id",
                            "new_window",
                            "parent_id",
                        )
                    }
                )
                record, _action = self._map_upsert(
                    "menu",
                    "%s/%s" % (parent_ref, item.target),
                    "website.menu",
                    vals,
                    digest,
                    create_vals={"sequence": position},
                )
                added[compare] = record
                state["count"] += 1
                position += 1
                if item.children:
                    place(item.children, record, item.target, 0)
            return position

        start = max(root.child_id.mapped("sequence") or [0]) + 1
        place(site.menu, root, "", start)

    # Redirects, blog style, home page, stale records

    def _write_redirects(self, site, records):
        """One 301 per /<ref>.php, per /<alias>.php and for /index.php.

        url_to is computed again on each run, since a post's URL follows
        its name. A rewrite of the same url_from that the import does not
        own is left alone, with rewrite_conflict.
        """
        website = self.website_id
        owned = (
            self.env["dolibarr.website.import.map"]
            .search(
                [
                    ("website_id", "=", website.id),
                    ("source_key", "=", self.source_key),
                    ("kind", "=", "redirect"),
                ]
            )
            .mapped("res_id")
        )
        pairs = {}
        for page in site.pages:
            record = records.get(page.ref)
            if not record:
                continue
            url_to = (
                record.url
                if record._name == "website.page"
                else record.website_url
            )
            for alias in [page.ref] + list(page.aliases):
                pairs.setdefault("/%s.php" % alias, url_to)
        pairs.setdefault("/index.php", "/")
        for url_from, url_to in pairs.items():
            if url_from == url_to:
                continue
            foreign = self.env["website.rewrite"].search(
                [
                    ("website_id", "in", (website.id, False)),
                    ("url_from", "=", url_from),
                    ("id", "not in", owned),
                ],
                limit=1,
            )
            if foreign:
                self._add_line(
                    finding("rewrite_conflict", url=url_from), foreign
                )
                continue
            vals = {
                "name": "Dolibarr %s: %s" % (self.source_key, url_from),
                "url_from": url_from,
                "url_to": url_to,
                "redirect_type": "301",
                "website_id": website.id,
            }
            digest = self._hash(
                {
                    "url_from": url_from,
                    "url_to": url_to,
                    "redirect_type": "301",
                }
            )
            self._map_upsert(
                "redirect", url_from, "website.rewrite", vals, digest
            )

    def _blog_style_arch(self, css, blog):
        """Extension of website.layout adding the site CSS to the posts
        of blog; built from fixed elements, css is a checked site path."""
        data = etree.Element("data")
        xpath = etree.SubElement(
            data, "xpath", {"expr": "//head", "position": "inside"}
        )
        cond = etree.SubElement(
            xpath,
            "t",
            {
                "t-if": "main_object and main_object._name == 'blog.post'"
                " and main_object.blog_id.id == %d" % int(blog.id)
            },
        )
        etree.SubElement(cond, "link", {"rel": "stylesheet", "href": css})
        return etree.tostring(data, encoding="unicode")

    def _write_blog_style(self, site, blog):
        """Site view inheriting this website's website.layout.

        Copy-on-write of website.layout moves the view to a copy with the
        same key, so the view is looked up by (key, website) when its map
        line points to a deleted record.
        """
        css = local_path(pipeline.css_url(site))
        if not self.style_blog_posts or not css:
            return
        website = self.website_id
        layout = website.with_context(website_id=website.id).viewref(
            "website.layout"
        )
        key = html2arch.blog_style_key(site.source_key)
        arch = self._blog_style_arch(css, blog)
        name = "Dolibarr import %s blog style" % site.source_key
        vals = {
            "name": name,
            "type": "qweb",
            "key": key,
            "website_id": website.id,
            "inherit_id": layout.id,
            "mode": "extension",
            "arch": arch,
        }
        digest = self._hash(
            {
                "arch_db": arch,
                "name": name,
                "active": True,
                "inherit_id": layout.key,
            }
        )
        self._map_upsert(
            "blog_style_view",
            "blog_style",
            "ir.ui.view",
            vals,
            digest,
            finder=lambda: self._view_by_key(key),
        )

    def _set_homepage(self, site, records):
        """With set_homepage, the website serves the source home page at
        /; without a source home page, or while its content was never
        written (an unpublished shell), nothing changes."""
        record = records.get(site.home_ref) if site.home_ref else None
        if not (
            self.set_homepage and record and record._name == "website.page"
        ):
            return
        if not self._map_line("page", site.home_ref).content_hash:
            return
        self.website_id.homepage_url = record.url

    def _report_stale(self, site):
        """One stale_record line per map line this run did not touch.

        Only a report: the record, its menu entry, its redirects and its
        map line stay as they are. A ref dropped by the page choices is
        told apart from one absent from the source. A page or post that
        the source still imports is never stale: when its write failed,
        its page_error line already reports it.
        """
        dropped = set(site.dropped_refs)
        present = {
            page.ref for page in site.pages if page.analysis_status == "import"
        }
        dropped_urls = {
            "/%s.php" % ref for ref in dropped | set(site.dropped_aliases)
        }
        env = self.env
        if self.lang:
            env = env(context=dict(env.context, lang=self.lang))
        by_choice_text = env._("dropped by choice")
        absent_text = env._("absent from source")
        lines = self.env["dolibarr.website.import.map"].search(
            [
                ("website_id", "=", self.website_id.id),
                ("source_key", "=", self.source_key),
                ("kind", "!=", "blog"),
                ("last_import_id", "!=", self.id),
            ]
        )
        for line in lines:
            if line.kind in ("page", "post") and line.ref in present:
                continue
            by_choice = (
                line.ref in dropped
                or line.ref in dropped_urls
                or any(
                    line.ref.endswith("/" + urls.PAGE + ref) for ref in dropped
                )
            )
            record = self.env[line.res_model].browse(line.res_id).exists()
            self._add_line(
                finding(
                    "stale_record",
                    page_ref=line.ref if line.kind in ("page", "post") else "",
                    kind=line.kind,
                    ref=line.ref,
                    reason=by_choice_text if by_choice else absent_text,
                ),
                record or None,
            )

    def _write_site(self, site, source, opts, deadline=None):
        """All writer passes, in a fixed order; returns ref -> record.

        blog, media, page and post records, rendering, site assets and
        head view, pages, posts, layout and menus, redirects, blog style,
        home page, stale records. The run's keep_scripts and
        style_blog_posts override those of opts, so the rendered HTML and
        the written assets follow one setting.
        """
        self._check_import_access()
        opts = dataclasses.replace(
            opts,
            keep_scripts=self.keep_scripts,
            style_blog_posts=self.style_blog_posts,
        )
        blog = self._ensure_blog()
        media = self._write_media(site, source, deadline)
        records = self._ensure_page_records(site, blog)
        resolver = WriterResolver(records, media, blog, self.website_id)
        rendered = pipeline.render_site(
            site, resolver, self._company_values(), opts
        )
        for item in rendered.findings:
            self._add_line(item)
        self._write_site_assets(site, rendered)
        self._write_pages(site, rendered, records, resolver, deadline)
        self._write_posts(site, rendered, records, resolver, blog, deadline)
        self._write_layout(site, rendered, records)
        self._write_redirects(site, records)
        self._write_blog_style(site, blog)
        self._set_homepage(site, records)
        self._report_stale(site)
        return records
