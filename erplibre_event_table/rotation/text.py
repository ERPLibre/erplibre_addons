# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import unicodedata


def normalize_company(label: str | None) -> str | None:
    """Return the grouping key of a company name, or None.

    NFKD decomposition, combining marks (category Mn) dropped, casefold,
    every non-alphanumeric character replaced with a space, spaces
    collapsed, stripped. An empty result becomes None, so that two
    spellings of one name yield the same key and an empty label creates
    no ghost company.
    """
    if label is None:
        return None

    decomposed = unicodedata.normalize("NFKD", label)
    without_marks = "".join(
        c for c in decomposed if not unicodedata.combining(c)
    )
    spaced = "".join(c if c.isalnum() else " " for c in without_marks)
    value = " ".join(spaced.casefold().split())
    return value or None
