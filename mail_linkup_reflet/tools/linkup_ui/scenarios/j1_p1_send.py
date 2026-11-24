# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Guide §5 P1: Sam writes a reflection in the Reflet view, folds the
complete card with a double-click and drags the token onto Jacques, with
the pointer of the browser; the card leaves at the drop (``p1_4``). The
keyboard variant of the drop ("Envoyer à…", arrows, Enter) is played by
P3.5 and P4, which send their reflections with it.

Jacques is logged in on his Reflet view before the sending, his sounds
recorded, so that P2.1 checks the "received" sound the carrier message
plays as it arrives.

The section leaves in ``run.memory["p1_reflet_id"]`` the id of the
reflection sent, waiting for Jacques in their direct conversation.
"""

import re

from selenium.webdriver.common.keys import Keys

from driver import StepFailure

SECTION = "P1"
TITLE = "Sam crée et envoie un reflet (guide §5 P1)"

YOU_SAID = "que la charge de toutes les tâches plus un travail t'épuise"
UNDERSTOOD = "tu es épuisée"
EMOTIONS_TITLE = "Tu m'as parlé de tes émotions"
SAM_CONTACTS = ("Jacques", "Jean", "France", "Mathieu", "Nicolas", "Joanna")

VIEW = ".o-linkup-RefletView"
FORM = ".o-linkup-RefletForm"
FORM_TITLE = ".o-linkup-RefletForm-title"
YOU_SAID_FIELD = ".o-linkup-RefletForm-youSaid"
UNDERSTOOD_FIELD = ".o-linkup-RefletForm-understood"
FOLD = ".o-linkup-RefletForm-fold"
TOKEN = ".o-linkup-RefletView-token"
CONTACT = ".o-linkup-RefletView-contact"
MENU_SECTION = ".o_menu_sections .dropdown-toggle, .o_menu_sections button"
MENU_ITEM = ".o-dropdown--menu .dropdown-item"


def quote(value):
    return "'%s'" % str(value).replace("'", "''")


def user(run, login):
    """``(user id, partner id, name)`` of ``login``."""
    row = run.sql(
        "SELECT u.id, u.partner_id, p.name FROM res_users u"
        " JOIN res_partner p ON p.id = u.partner_id"
        f" WHERE u.login = {quote(login)}"
    )[0]
    return int(row[0]), int(row[1]), row[2]


def draft_of(run, login):
    """``(id, category code, French card title, you_said)`` of the draft
    of ``login``, or None."""
    rows = run.sql(
        "SELECT r.id, c.code, c.reflet_title->>'fr_CA', coalesce(r.you_said, '')"
        " FROM linkup_reflet r JOIN linkup_category c ON c.id = r.category_id"
        " JOIN res_users u ON u.id = r.author_id"
        f" WHERE r.state = 'draft' AND u.login = {quote(login)}"
    )
    return rows[0] if rows else None


def ledger_count(run, login):
    return int(
        run.sql(
            "SELECT count(*) FROM linkup_points_ledger l"
            " JOIN res_users u ON u.id = l.user_id"
            f" WHERE u.login = {quote(login)}"
        )[0][0]
    )


def field_value(persona, css):
    return persona.find(css).get_property("value")


def open_reflet_view(persona):
    """Discussion › LinkUp › Vue Reflet, then wait for the loaded view."""
    persona.click(MENU_SECTION, "LinkUp")
    persona.click(MENU_ITEM, "Vue Reflet")
    persona.find(f"{VIEW} .o-linkup-RefletView-body")


def ensure_reflet_view(persona):
    """The Reflet view of a member who just logged in, or opened from the
    menu when the landing page is another one."""
    try:
        persona.find(f"{VIEW} .o-linkup-RefletView-body", timeout=8)
    except StepFailure:
        open_reflet_view(persona)


def p1_1(run):
    sam = run.persona("sam")
    open_reflet_view(sam)
    _uid, _pid, name = user(run, "sam")
    header = sam.text(".o-linkup-RefletView-header")
    run.check(
        name in header, f"nom « {name} » absent de l'en-tête : {header!r}"
    )
    sam.find(".o-linkup-HelpBar .o-linkup-HelpBar-category")
    sam.find(".o-linkup-RefletView-card")
    sam.find(".o-linkup-RefletView-newlink")
    newlink = sam.text(".o-linkup-RefletView-newlink")
    run.check("+ NewLink" in newlink, f"bouton NewLink : {newlink!r}")
    sam.find(".o-linkup-RefletView-contact")
    names = [e.text.strip() for e in sam.finds(".o-linkup-RefletView-name")]
    missing = [c for c in SAM_CONTACTS if c not in names]
    run.check(not missing, f"contacts absents : {missing} (vus : {names})")

    draft = draft_of(run, "sam")
    run.check(draft is not None, "aucun brouillon de sam en base")
    draft_id, code, title, you_said = draft
    run.check(code == "vulnerability", f"brouillon de catégorie {code}")
    run.check(title, "titre fr_CA manquant")
    sam.find(f"{FORM_TITLE} svg[data-code='vulnerability']")
    form_title = sam.text(FORM_TITLE)
    run.check(
        title in form_title,
        f"titre de la carte : {form_title!r}, attendu {title!r}",
    )
    shown = field_value(sam, YOU_SAID_FIELD)
    run.check(
        shown == you_said, f"« Tu m'as dit » : {shown!r}, attendu {you_said!r}"
    )
    run.memory["p1_draft"] = {"id": int(draft_id), "you_said": you_said}
    return f"brouillon {title} rouvert ; contacts : {', '.join(names)}"


def p1_2(run):
    sam = run.persona("sam")
    kept = run.memory["p1_draft"]["you_said"]
    before_understood = field_value(sam, UNDERSTOOD_FIELD)
    sam.click(".o-linkup-HelpBar-category[data-code='emotions']")
    sam.find(
        ".o-linkup-HelpBar-category[data-code='emotions'][aria-pressed='true']"
    )
    sam.find(f"{FORM_TITLE} svg[data-code='emotions']")
    sam.find_text(FORM_TITLE, EMOTIONS_TITLE)
    run.check(
        not sam.finds(f"{FORM_TITLE} svg[data-code='vulnerability']"),
        "l'icône Vulnérabilité reste dans le titre",
    )
    you_said = field_value(sam, YOU_SAID_FIELD)
    run.check(
        you_said == kept, f"« Tu m'as dit » : {you_said!r}, attendu {kept!r}"
    )
    understood = field_value(sam, UNDERSTOOD_FIELD)
    run.check(
        understood == before_understood,
        f"« J'ai compris que » : {understood!r}, avant {before_understood!r}",
    )
    return f"titre « {EMOTIONS_TITLE} », texte conservé"


def p1_3(run):
    sam = run.persona("sam")
    sam.type(YOU_SAID_FIELD, YOU_SAID)
    sam.type(UNDERSTOOD_FIELD, UNDERSTOOD)
    run.check(
        field_value(sam, YOU_SAID_FIELD) == YOU_SAID,
        "« Tu m'as dit » mal saisi",
    )
    run.check(
        field_value(sam, UNDERSTOOD_FIELD) == UNDERSTOOD,
        "« J'ai compris que » mal saisi",
    )
    sam.click(".o-linkup-RefletForm-previewButton", "Aperçu")
    card = ".o-linkup-RefletForm-preview .o-linkup-RefletCard"
    sam.find(f"{card} svg[data-code='emotions']")
    sam.find_text(f"{card} .o-linkup-RefletCard-title", EMOTIONS_TITLE)
    sam.find_text(f"{card} .o-linkup-RefletCard-youSaid", YOU_SAID)
    sam.find_text(f"{card} .o-linkup-RefletCard-understood", UNDERSTOOD)
    # The preview follows the form while it stays open.
    sam.type(UNDERSTOOD_FIELD, "!", clear=False)
    sam.find_text(f"{card} .o-linkup-RefletCard-understood", UNDERSTOOD + "!")
    sam.keys(Keys.BACKSPACE, css=UNDERSTOOD_FIELD)
    sam.wait_until(
        lambda d: sam.text(f"{card} .o-linkup-RefletCard-understood").endswith(
            UNDERSTOOD
        ),
        "aperçu revenu au texte saisi",
    )
    return "aperçu : titre, textes, mise à jour à la frappe"


def pick_in_list(run, persona, name):
    """Walk the open "Envoyer à…" list with the down arrow to ``name``.
    Each key waits for the active option to move, since the list renders
    after the keydown."""
    picker = ".o-linkup-RefletView-picker"
    option = f"{picker} .o-linkup-RefletView-option"
    persona.find(f"{picker}:focus")
    names = [e.text.strip() for e in persona.finds(option)]
    run.check(
        name in names, f"« {name} » absent de la liste Envoyer à… : {names}"
    )
    active = persona.find(f"{option}.o-isActive").text.strip()
    index = names.index(active)
    while names[index] != name:
        persona.keys(Keys.ARROW_DOWN, css=picker)
        index = (index + 1) % len(names)
        persona.find_text(f"{option}.o-isActive", names[index])


def p1_4(run):
    sam = run.persona("sam")
    jacques_id, jacques_pid, jacques_name = user(run, "jacques")
    sam_id, sam_pid, _ = user(run, "sam")
    karma = {login: run.points(login) for login in ("sam", "jacques")}
    ledger = {login: ledger_count(run, login) for login in ("sam", "jacques")}
    to_jacques = (
        f"r.author_id = {sam_id} AND r.recipient_id = {jacques_id}"
        " AND r.kind = 'initial'"
    )
    count = f"SELECT count(*) FROM linkup_reflet r WHERE {to_jacques}"
    before = run.sql(count)
    run.check(
        before == [["0"]], f"reflets de Sam à Jacques déjà présents : {before}"
    )

    jacques = run.persona("jacques")
    ensure_reflet_view(jacques)
    jacques.record_sounds()
    sam.record_sounds()

    # The fold: "Plier" is offered, and a double-click on the card folds
    # it into a token holding its icon and the beginning of its text.
    run.check(
        not sam.has(
            ".o-linkup-RefletView-recipient .fw-bold", f"À : {jacques_name}"
        ),
        "Jacques est déjà le destinataire avant le dépôt",
    )
    sam.find_text(FOLD, "Plier")
    sam.dblclick(FORM_TITLE, EMOTIONS_TITLE)
    sam.find(f"{TOKEN} svg[data-code='emotions']")
    sam.wait_gone(FORM)
    sam.find(f"{TOKEN}:focus")
    token_text = sam.text(f"{TOKEN} .o-linkup-RefletView-tokenText")
    run.check(
        token_text.rstrip("…") and YOU_SAID.startswith(token_text.rstrip("…")),
        f"texte du jeton : {token_text!r}, début attendu de {YOU_SAID!r}",
    )
    label = sam.find(TOKEN).get_attribute("aria-label") or ""
    run.check(
        label.startswith("Carte pliée") and EMOTIONS_TITLE in label,
        f"nom accessible du jeton : {label!r}",
    )

    # The drop: the token onto the row of Jacques, whose row and avatar
    # zoom while the token is over them.
    jacques_row = f"{CONTACT}[data-user-id='{jacques_id}']"

    def avatar_scale():
        """The horizontal scale of the avatar of Jacques, read from its
        computed ``matrix(a, b, c, d, e, f)``; 1 without a transform."""
        transform = sam.js(
            "return getComputedStyle(arguments[0]).transform;",
            sam.find(f"{jacques_row} .o-linkup-RefletView-avatar"),
        )
        match = re.match(r"matrix\(\s*([-\d.e]+)", transform or "")
        return float(match.group(1)) if match else 1.0

    def zoomed():
        """The scale of the avatar once its transition ends at 1.3."""
        sam.find(f"{jacques_row}.o-isDropTarget")
        sam.wait_until(
            lambda _d: abs(avatar_scale() - 1.3) < 0.01,
            f"avatar de {jacques_name} agrandi à 1.3 au survol",
            timeout=3,
        )
        return avatar_scale()

    scale = sam.drag(TOKEN, jacques_row, while_over=zoomed)
    run.check(
        abs(scale - 1.3) < 0.01,
        f"échelle de l'avatar de {jacques_name} au survol : {scale}",
    )
    sam.find_text(
        ".o-linkup-RefletView-notice", f"Reflet envoyé à {jacques_name}."
    )
    sam.find(".o-linkup-RefletView-sentChat:focus")
    sam.wait_until(
        lambda _d: any("linkup_sent" in s for s in sam.played_sounds()),
        "son « envoyé » joué chez Sam",
    )

    rows = run.sql(
        "SELECT r.id, r.state, c.code, r.you_said, r.understood, r.channel_id,"
        " ch.channel_type, r.message_id, m.model, m.res_id"
        " FROM linkup_reflet r JOIN linkup_category c ON c.id = r.category_id"
        " LEFT JOIN discuss_channel ch ON ch.id = r.channel_id"
        " LEFT JOIN mail_message m ON m.id = r.message_id"
        f" WHERE {to_jacques}"
    )
    run.check(len(rows) == 1, f"{len(rows)} reflet(s) créé(s) pour Jacques")
    (
        rid,
        state,
        code,
        you_said,
        understood,
        channel,
        ctype,
        message,
        model,
        res_id,
    ) = rows[0]
    run.check(state == "sent", f"état du reflet : {state}")
    run.check(code == "emotions", f"catégorie du reflet : {code}")
    run.check(
        (you_said, understood) == (YOU_SAID, UNDERSTOOD),
        f"textes enregistrés : {you_said!r} / {understood!r}",
    )
    run.check(ctype == "chat", f"canal {channel} de type {ctype}")
    members = {
        int(r[0])
        for r in run.sql(
            f"SELECT partner_id FROM discuss_channel_member WHERE channel_id = {channel}"
        )
    }
    run.check(
        members == {sam_pid, jacques_pid},
        f"membres du canal {channel} : {sorted(members)}",
    )
    run.check(
        message and model == "discuss.channel" and res_id == channel,
        f"message {message} posté sur {model} {res_id}",
    )
    after_karma = {login: run.points(login) for login in karma}
    after_ledger = {login: ledger_count(run, login) for login in ledger}
    run.check(
        after_karma == karma, f"points à l'envoi : {karma} → {after_karma}"
    )
    run.check(
        after_ledger == ledger,
        f"lignes du registre : {ledger} → {after_ledger}",
    )
    run.memory["p1_reflet_id"] = int(rid)
    run.memory["p1_channel_id"] = int(channel)
    return (
        f"carte pliée au double-clic, jeton « {token_text} » glissé sur"
        f" {jacques_name} (pointeur, avatar ×{scale:.2f}) : reflet {rid}"
        f" dans le canal direct {channel} ; points inchangés {karma}"
    )


def p1_5(run):
    sam = run.persona("sam")
    jacques_id, _pid, jacques_name = user(run, "jacques")
    row = f".o-linkup-RefletView-contact[data-user-id='{jacques_id}']"
    sam.close_notifications()
    sam.click(f"{row} .o-linkup-RefletView-openChat")
    sam.find(f".o-mail-Discuss-threadName[title='{jacques_name}']")
    sam.pass_tour()
    card = ".o-mail-Message .o-linkup-RefletCard[data-state='sent'][data-role='author']"
    sam.find_text(f"{card} .o-linkup-RefletCard-understood", UNDERSTOOD)
    sam.find_text(f"{card} .o-linkup-RefletCard-title", EMOTIONS_TITLE)
    badge = sam.text(f"{card} .o-linkup-RefletCard-badge")
    run.check(badge == "En attente", f"badge de la carte : {badge!r}")
    sam.find_text(
        f"{card} .o-linkup-RefletActions-withdraw", "Retirer ce reflet"
    )
    read = run.sql(
        f"SELECT read_date IS NULL FROM linkup_reflet WHERE id = {run.memory['p1_reflet_id']}"
    )
    run.check(read == [["t"]], f"reflet déjà lu par Jacques : {read}")
    return "carte « En attente », « Retirer ce reflet » offert"


STEPS = [
    (
        "P1.1",
        "Vue Reflet : Sam, barre Help, carte, contacts, + NewLink ; brouillon Vulnérabilité rouvert",
        p1_1,
    ),
    (
        "P1.2",
        "Émotions : icône et titre « Tu m'as parlé de tes émotions » ; texte conservé",
        p1_2,
    ),
    ("P1.3", "Saisie des deux textes : aperçu de la carte à jour", p1_3),
    (
        "P1.4",
        "Plier la carte (double-clic, bouton « Plier »), glisser le jeton sur Jacques : son « envoyé », carte dans le direct Sam–Jacques, aucun point",
        p1_4,
    ),
    (
        "P1.5",
        "Conversation Sam–Jacques : carte « envoyé », Sam peut la retirer",
        p1_5,
    ),
]
