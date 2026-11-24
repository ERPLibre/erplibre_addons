# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
"""Values shared by the signup, the profile and NewLink of the community."""

import re
import secrets

# Age ranges a person declares at signup (LU-F-111 RM2): a range, never a
# date of birth. Every range starts at 18 (Q-22).
AGE_BRACKETS = [
    ("18_24", "18 to 24"),
    ("25_34", "25 to 34"),
    ("35_44", "35 to 44"),
    ("45_54", "45 to 54"),
    ("55_64", "55 to 64"),
    ("65_plus", "65 and over"),
]

# Jurisdictions the public signup accepts (Q-32): a declaration of the
# person, without any geolocation.
JURISDICTIONS = [("CA", "Canada")]

# Who may send the member a first reflection (LU-F-016 RM7).
FIRST_REFLET_SCOPES = [
    ("nobody", "Nobody"),
    ("code", "With my code"),
    ("email_or_code", "With my email address or my code"),
]

# Fields of the signup form of the community, posted with those of
# ``auth_signup``. ``linkup_website`` is a trap a person never sees.
SIGNUP_FIELDS = (
    "linkup_terms",
    "linkup_privacy",
    "linkup_sensitive_data",
    "linkup_link_visibility",
    "linkup_energy_visibility",
    "linkup_notifications",
    "linkup_adult",
    "linkup_age_bracket",
    "linkup_resides_canada",
    "linkup_phone",
    "linkup_website",
)

# Letters and digits of a personal code, without those read one for the
# other (I, L, O, 0, 1).
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10

# Prefix of the technical login of an account of the community: the login
# never holds the address (LU-F-113 RM2).
LOGIN_PREFIX = "lu-"


def new_login():
    """A random technical login."""
    return LOGIN_PREFIX + secrets.token_hex(8)


def new_code():
    """A random personal code, ``CODE_LENGTH`` characters of
    ``CODE_ALPHABET``."""
    return "".join(
        secrets.choice(CODE_ALPHABET) for _index in range(CODE_LENGTH)
    )


def normalize_code(value):
    """A code as typed, upper case, without blanks nor dashes; ``""`` when
    it cannot be a code."""
    if not isinstance(value, str):
        return ""
    code = re.sub(r"[\s-]+", "", value).upper()
    if len(code) != CODE_LENGTH or any(c not in CODE_ALPHABET for c in code):
        return ""
    return code


def format_code(code):
    """A code in two groups of five, as the member reads it."""
    return f"{code[:5]}-{code[5:]}" if code else ""


def normalize_phone(value):
    """The digits of a phone number, with a leading ``+`` kept; ``""`` when
    it holds fewer than 7 or more than 15 digits."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not re.fullmatch(r"\+?[\d\s().-]+", text):
        return ""
    digits = re.sub(r"\D", "", text)
    if not 7 <= len(digits) <= 15:
        return ""
    return ("+" if text.startswith("+") else "") + digits


def phones_match(first, second):
    """Whether two numbers name the same phone: their last ten digits when
    both hold that many, so that a country prefix makes no difference,
    otherwise all of them."""
    first = re.sub(r"\D", "", first or "")
    second = re.sub(r"\D", "", second or "")
    if not first or not second:
        return False
    if len(first) >= 10 and len(second) >= 10:
        return first[-10:] == second[-10:]
    return first == second


def mask_phone(phone):
    """The number as the inviter sees it after sending: its last two
    digits only."""
    digits = re.sub(r"\D", "", phone or "")
    return f"•••{digits[-2:]}" if digits else "•••"
