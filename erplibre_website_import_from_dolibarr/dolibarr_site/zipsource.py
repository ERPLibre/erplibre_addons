# Copyright 2026 TechnoLibre (https://technolibre.ca)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Safe in-memory reading of a Dolibarr website export zip.

The end of central directory record is read first, so the entry count and
the central directory size are bounded before zipfile builds its index.
Nothing is ever extracted to disk: entries are read in chunks under a byte
cap, and zipfile stops at the declared size (a lying header raises a CRC
error), so declared sizes are checked before any read. A media file over
the per-file cap is skipped and reported; every other cap refuses the zip.
"""

import dataclasses
import io
import os
import posixpath
import re
import stat
import struct
import unicodedata
import zipfile
import zlib

import chardet

from . import sqldump
from .messages import finding
from .model import (
    Media,
    Page,
    Site,
    SourceError,
    primary_lang,
    slugify_ref,
    valid_key,
    valid_lang,
    valid_ref,
    valid_relpath,
)

MIB = 1024 * 1024
_EOCD = b"PK\x05\x06"
_Z64_LOCATOR = b"PK\x06\x07"
_Z64_EOCD = b"PK\x06\x06"
_CD_HEADER = b"PK\x01\x02"
_FILENAME = re.compile(r"^website_(?P<ref>.+?)-\d{14}-V[\d.]+\.zip$")
_FILENAME_STOCK = re.compile(r"^website_(?P<ref>.+)\.zip$")
_INTEGER = re.compile(r"-?[0-9]{1,18}")
_PLACEHOLDER = re.compile(r"__(?:\([^)]*\)|\[[^\]]*\]|\d+)__")
_CONTAINERS = (
    ("head_assets", "containers/htmlheader.html"),
    ("site_css", "containers/styles.css.php"),
    ("site_js", "containers/javascript.js.php"),
)


@dataclasses.dataclass
class ZipLimits:
    max_entries: int = 10000
    max_total: int = 512 * MIB
    max_sql: int = 16 * MIB
    max_container: int = 5 * MIB
    max_media: int = 20 * MIB
    max_ratio: int = 100
    max_central_directory: int = 16 * MIB

    @classmethod
    def from_options(cls, overrides):
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(
            **{k: int(v) for k, v in (overrides or {}).items() if k in names}
        )


def _count_headers(data, start, end, limit):
    """Count central directory file headers in the raw bytes.

    The directory must be exactly the headers from start to end: any other
    signature, or a header running past end, is refused. The count is
    bounded by limit + 1 headers, whatever the end record claims.
    """
    if start < 0 or start > end:
        raise SourceError("zip central directory lies outside the file")
    count = 0
    offset = start
    while offset < end:
        if offset + 46 > end or data[offset : offset + 4] != _CD_HEADER:
            raise SourceError("zip central directory is malformed")
        count += 1
        if count > limit:
            raise SourceError("zip has more than %d entries" % limit)
        name, extra, comment = struct.unpack_from("<HHH", data, offset + 28)
        offset += 46 + name + extra + comment
    if offset != end:
        raise SourceError("zip central directory is malformed")
    return count


def _check_eocd(data, limits):
    """Bound entry count and central directory size from the raw bytes.

    Like zipfile, a zip64 locator right before the end record means the
    zip64 record sits at EOCD-76, whatever the locator's own offset says;
    a locator that disagrees is refused. The capped values are the ones
    zipfile will use, and the central directory, which ends where the
    record begins, is then walked header by header.
    """
    pos = data.rfind(_EOCD, max(0, len(data) - 65557))
    if pos < 0 or len(data) < pos + 22:
        raise SourceError("not a zip file: end of central directory missing")
    try:
        entries, cd_size = struct.unpack_from("<HI", data, pos + 10)
        cd_end = pos
        loc = pos - 20
        if loc >= 0 and data[loc : loc + 4] == _Z64_LOCATOR:
            record = pos - 76
            (offset,) = struct.unpack_from("<Q", data, loc + 8)
            if record < 0 or offset != record:
                raise SourceError("broken zip64 end of central directory")
            if data[record : record + 4] != _Z64_EOCD:
                raise SourceError("broken zip64 end of central directory")
            entries, cd_size = struct.unpack_from("<QQ", data, record + 32)
            cd_end = record
        elif entries == 0xFFFF or cd_size == 0xFFFFFFFF:
            raise SourceError("broken zip64 end of central directory locator")
        if entries > limits.max_entries:
            raise SourceError(
                "zip has %d entries, more than %d"
                % (entries, limits.max_entries)
            )
        if cd_size > limits.max_central_directory:
            raise SourceError("zip central directory is %d bytes" % cd_size)
        _count_headers(data, cd_end - cd_size, cd_end, limits.max_entries)
    except struct.error as exc:
        raise SourceError("truncated zip end of central directory") from exc


class ZipSource:
    """Validated view of an uploaded zip; entries are read on demand."""

    def __init__(self, data, limits=None):
        self.limits = limits or ZipLimits()
        _check_eocd(data, self.limits)
        try:
            self._zip = zipfile.ZipFile(io.BytesIO(data))
            infos = self._zip.infolist()
        except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError) as exc:
            raise SourceError("not a valid zip file: %s" % exc) from exc
        if len(infos) > self.limits.max_entries:
            raise SourceError("zip has %d entries" % len(infos))
        self._entries = {}
        total = 0
        for info in infos:
            name = info.filename
            if info.flag_bits & 0x1:
                raise SourceError("encrypted zip entry %r" % name)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise SourceError("symbolic link in zip: %r" % name)
            unix = name.replace("\\", "/")
            if (
                unix.startswith("/")
                or re.match(r"^[A-Za-z]:", unix)
                or ".." in unix.split("/")
            ):
                raise SourceError("unsafe zip entry name %r" % name)
            if info.is_dir():
                continue
            norm = unicodedata.normalize("NFC", posixpath.normpath(unix))
            if norm in self._entries:
                raise SourceError("duplicate zip entry %r" % name)
            if info.file_size / max(info.compress_size, 1) > (
                self.limits.max_ratio
            ):
                raise SourceError("zip entry %r is over-compressed" % name)
            total += info.file_size
            self._entries[norm] = info
        if total > self.limits.max_total:
            raise SourceError("zip expands to %d bytes" % total)

    def names(self):
        return sorted(self._entries)

    def has(self, name):
        return name in self._entries

    def size(self, name):
        return self._entries[name].file_size

    def read(self, name, limit):
        info = self._entries[name]
        if info.file_size > limit:
            raise SourceError(
                "zip entry %r is %d bytes, over %d"
                % (name, info.file_size, limit)
            )
        out = bytearray()
        try:
            with self._zip.open(info) as handle:
                while True:
                    chunk = handle.read(65536)
                    if not chunk:
                        break
                    out += chunk
                    if len(out) > limit:
                        raise SourceError(
                            "zip entry %r exceeds its size" % name
                        )
        except SourceError:
            raise
        except (
            zipfile.BadZipFile,
            NotImplementedError,
            zlib.error,
            struct.error,
            EOFError,
            OSError,
            ValueError,
            RuntimeError,
        ) as exc:
            raise SourceError(
                "zip entry %r cannot be read (%s)" % (name, type(exc).__name__)
            ) from exc
        return bytes(out)

    def read_media(self, media):
        return self.read(media.zip_name, self.limits.max_media)


def key_from_filename(filename):
    base = re.split(r"[\\/]", filename or "")[-1]
    match = _FILENAME.match(base) or _FILENAME_STOCK.match(base)
    return match.group("ref") if match else ""


def decode_text(data):
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        encoding = chardet.detect(data).get("encoding") or "latin-1"
        return data.decode(encoding, errors="replace")


def find_placeholders(text):
    """make_substitutions tokens an export can keep: shown as text."""
    return _PLACEHOLDER.findall(text or "")


def read_zip_file(path, limit):
    """Bytes of the zip file at path, read under limit bytes.

    Only a regular file is read: a device, a FIFO or a symlink to one is
    refused. The file is opened without blocking and checked again on its
    descriptor, so a swap between the check and the open changes nothing,
    and the read stops one byte past the limit whatever the size said.
    """
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode):
        raise SourceError("%s is not a regular file" % path)
    if info.st_size > limit:
        raise SourceError(
            "zip file is %d bytes, over the %d-byte limit"
            % (info.st_size, limit)
        )
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise SourceError("%s is not a regular file" % path)
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise SourceError("zip file is over the %d-byte limit" % limit)
    return data


def open_zip(data, opts):
    return ZipSource(data, ZipLimits.from_options(opts.zip_limits))


def _ref_or_slug(raw, site):
    ref = _slug(raw)
    if ref != raw:
        site.findings.append(
            finding("ref_slugified", page_ref=ref, original=raw, ref=ref)
        )
    return ref


def _slug(raw):
    return raw if valid_ref(raw) else slugify_ref(raw)


def _row_int(value):
    """Integer of a rowid or fk_page value, or None when it is not one.

    NULL gives 0; a string counts only when it is a whole number of at
    most 18 digits.
    """
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return int(text) if _INTEGER.fullmatch(text) else None


def _row_error(site, ref, seen, reason):
    """Report a skipped row with page_error; seen["errors"] keeps it.

    The finding belongs to no page when a kept page holds the row's ref,
    so the page that imports never shows the error: _detach_row_errors()
    applies the rule to a ref kept by a later row.
    """
    page_ref = "" if ref in seen["refs"] else ref
    item = finding("page_error", page_ref=page_ref, ref=ref, reason=reason)
    site.findings.append(item)
    seen["errors"].append(item)


def _detach_row_errors(seen):
    """Move to the site level the row errors whose ref a kept page holds."""
    for item in seen["errors"]:
        if item.page_ref in seen["refs"]:
            item.page_ref = ""


def _page_from_row(row, key, site, seen):
    """Build a raw Page from one INSERT row; None when the page is skipped.

    seen holds the refs and the non-zero rowids of the rows already kept:
    a later row whose ref (as written or once slugified) or rowid is taken
    is skipped as a duplicate, and its page_error names it by its rowid.
    Only a kept row reports its ref as slugified.
    """
    raw_ref = str(row.get("pageurl") or "")
    ref = _slug(raw_ref)
    source_id = _row_int(row.get("rowid"))
    fk_page = _row_int(row.get("fk_page"))
    for column, number in (("rowid", source_id), ("fk_page", fk_page)):
        if number is None:
            value = str(row.get(column))[:20]
            reason = "invalid %s %r" % (column, value)
            if column != "rowid":
                reason = "row %d: %s" % (source_id, reason)
            _row_error(site, ref, seen, reason)
            return None
    for what, taken in (
        ("rowid", source_id and source_id in seen["ids"]),
        ("ref", ref in seen["refs"]),
    ):
        if taken:
            _row_error(
                site,
                ref,
                seen,
                "row %d is a duplicate %s of an earlier row"
                % (source_id, what),
            )
            return None
    lang_raw = str(row.get("lang") or "").strip()
    if not valid_lang(lang_raw):
        _row_error(
            site,
            ref,
            seen,
            "row %d: invalid language %r" % (source_id, lang_raw[:20]),
        )
        return None
    ref = _ref_or_slug(raw_ref, site)
    aliases = []
    for alias in str(row.get("aliasalt") or "").split(","):
        alias = alias.strip()
        if alias:
            aliases.append(_ref_or_slug(alias, site))

    def text(column):
        value = row.get(column)
        value = "" if value is None else str(value)
        return value.replace("__WEBSITE_KEY__", key)

    return Page(
        ref=ref,
        aliases=aliases,
        dolibarr_type=text("type_container") or "page",
        source_id=source_id,
        fk_page=fk_page,
        title=text("title"),
        description=text("description"),
        keywords=text("keywords"),
        lang=primary_lang(lang_raw),
        image_relpath=text("image"),
        author_alias=text("author_alias"),
        date_creation=text("date_creation"),
        published=str(row.get("status")) == "1",
        head_html=text("htmlheader"),
        body_html=text("content"),
    )


def _list_media(source, key, site):
    prefixes = []
    for kind in ("image", "js"):
        for folder in ("websitekey", key):
            prefixes.append(("medias/%s/%s/" % (kind, folder), kind, folder))
    chosen = {}
    for name in source.names():
        for prefix, kind, folder in prefixes:
            if not name.startswith(prefix):
                continue
            relpath = "%s/%s/%s" % (kind, key, name[len(prefix) :])
            if not valid_relpath(relpath, key):
                site.findings.append(
                    finding("media_name_refused", relpath=relpath)
                )
            elif source.size(name) > source.limits.max_media:
                site.findings.append(
                    finding(
                        "media_too_large",
                        relpath=relpath,
                        limit=source.limits.max_media,
                    )
                )
            elif relpath in chosen and folder != key:
                site.findings.append(
                    finding("media_duplicate", relpath=relpath)
                )
            else:
                if relpath in chosen:
                    site.findings.append(
                        finding("media_duplicate", relpath=relpath)
                    )
                chosen[relpath] = Media(
                    relpath=relpath, size=source.size(name), zip_name=name
                )
            break
    return list(chosen.values())


def load_zip(data, opts, source=None):
    """Read an export zip into a raw Site: pages keep their PHP."""
    source = source or open_zip(data, opts)
    key = opts.source_key or key_from_filename(opts.filename)
    if not valid_key(key):
        raise SourceError("invalid website key %r" % key[:80])
    if not source.has("website_pages.sql"):
        raise SourceError("website_pages.sql is missing from the zip")
    dump = sqldump.parse(
        decode_text(source.read("website_pages.sql", source.limits.max_sql))
    )
    if not dump.rows:
        raise SourceError(
            "not a Dolibarr website: website_pages.sql has no"
            " llx_website_page row"
        )
    site = Site(source_key=key, dolibarr_version=dump.version)
    locale = dump.lang.strip()
    if not locale or not valid_lang(locale):
        locale = opts.default_lang or "en"
        site.findings.append(
            finding("main_lang_defaulted", lang=primary_lang(locale))
        )
    site.lang_locale = locale
    site.main_lang = primary_lang(locale)
    site.other_langs = [
        primary_lang(code.strip())
        for code in dump.otherlang.split(",")
        if code.strip() and valid_lang(code.strip())
    ]
    by_id, seen = {}, {"refs": set(), "ids": set(), "errors": []}
    for row in dump.rows:
        page = _page_from_row(row, key, site, seen)
        if page is not None:
            seen["refs"].add(page.ref)
            site.pages.append(page)
            if page.source_id:
                seen["ids"].add(page.source_id)
                by_id[page.source_id] = page
    _detach_row_errors(seen)
    if dump.home_id in by_id:
        site.home_ref = by_id[dump.home_id].ref
    for attr, name in _CONTAINERS:
        if source.has(name):
            raw = decode_text(source.read(name, source.limits.max_container))
            setattr(site, attr, raw.replace("__WEBSITE_KEY__", key))
    for name in ("README.md", "LICENSE"):
        if source.has(name):
            raw = decode_text(source.read(name, source.limits.max_container))
            site.findings.append(
                finding("credits", file=name, text=" ".join(raw.split())[:300])
            )
    site.media = _list_media(source, key, site)
    return site
