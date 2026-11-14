# Copyright 2026 TechnoLibre (http://www.technolibre.ca)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Guide §6: NewLink by email, without any outgoing mail server.

Sam invites a person who is not a member from "+ NewLink"; the email
stays queued in the database, where the step reads its link. The link is
opened in a browser that is logged in nowhere (the private window of the
guide), and the person signs up with the invited address. Then the
controls of point 4: the used link, a cancelled invitation, the refusal
of every invitation (``/optout``), a link used with another address.

The tokens of the links exist in clear only in the bodies of the queued
emails; they stay in ``run.memory`` and never go to a note. The accounts
created here get random passwords that live in this process only.
"""

import html
import os
import re
import secrets
import time

from selenium.webdriver.common.keys import Keys

from driver import SETTLE, Persona
from .j1_p1_send import MENU_ITEM, MENU_SECTION, open_reflet_view, quote, user
from .j1_p2_validate import RECEIVED, card_holding, click_in, open_chat_with

SECTION = "N"
TITLE = "NewLink par courriel, en local (guide §6)"

DOMAIN = "example.com"
# Invented addresses and names, under the reserved domain.
INVITED = {
    "signup": ("invite.recette1@example.com", "Camille", "emotions"),
    "cancel": ("invite.recette2@example.com", "Dominique", "needs"),
    "other": ("invite.recette3@example.com", "Gabrielle", "goals"),
}
OTHER_ADDRESS = "autre.recette4@example.com"
SIGNUP_NAMES = {"signup": "Camille Recette", "other": "Alex Recette"}
YOU_SAID = "que tu reprends des études le soir en plus de ton emploi"
UNDERSTOOD = "tu as hâte d'avoir plus de temps pour toi"

VIEW = ".o-linkup-RefletView"
NEWLINK = ".o-linkup-Newlink"
INVITE_PAGE = ".o-linkup-InvitePage"
CONTACT = ".o-linkup-RefletView-contact"
MAIL_CRON = "ir_cron_mail_scheduler_action"
LINK_RE = r"(https?://[^\s\"'<>]+)/linkup/invite/([A-Za-z0-9_-]{20,100})"

MAIL_SUBJECT = "{name} souhaite te faire un reflet sur LinkUp"
MAIL_TEXTS = (
    "Bonjour,",
    "Une personne que tu as rencontrée, {name}, souhaite te faire un reflet sur LinkUp.",
    "Son texte n'est pas dans ce courriel",
    "Voir le reflet et m'inscrire",
    "Lien personnel, valable 14 jours, pour une seule inscription.",
    "Ne plus jamais recevoir d'invitation LinkUp",
)
PAGE_INTRO = "Une personne que tu as rencontrée, {name}, souhaite te faire un reflet sur LinkUp."
PAGE_USED = "Cette invitation a déjà servi."
PAGE_CANCELLED = (
    "Cette invitation a été annulée par la personne qui l'a envoyée."
)
PAGE_OPTOUT_DONE = (
    "C'est fait : LinkUp n'enverra plus aucune invitation à cette adresse."
)
# The first invitation of the day of Sam, out of the daily limit.
QUOTA_AFTER_FIRST = "Invitations aujourd'hui : 1 sur 10"
NEW_ACCOUNT_REASON = "Compte trop récent"
CANCELLED_TEXT = "Invitation annulée. Le lien ne fonctionne plus. Ton reflet est revenu dans tes brouillons."


# Database ------------------------------------------------------------


def masked(email):
    local, _sep, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def invitation_of(run, email):
    """``{id, state, reflet_id, reflet_state, recipient}`` of the latest
    invitation of Sam to ``email``, or None."""
    rows = run.sql(
        "SELECT i.id, i.state, coalesce(i.reflet_id, 0), coalesce(r.state, ''),"
        " coalesce(r.recipient_id, 0), coalesce(i.name, '')"
        " FROM linkup_invitation i LEFT JOIN linkup_reflet r ON r.id = i.reflet_id"
        " JOIN res_users u ON u.id = i.inviter_id"
        f" WHERE u.login = 'sam' AND i.email = {quote(email)} ORDER BY i.id DESC LIMIT 1"
    )
    if not rows:
        return None
    keys = ("id", "state", "reflet_id", "reflet_state", "recipient", "name")
    row = dict(zip(keys, rows[0]))
    for key in ("id", "reflet_id", "recipient"):
        row[key] = int(row[key])
    return row


def reflet(run, reflet_id):
    """``{state, category, you_said, understood, real_world, recipient,
    read}`` of a reflection."""
    row = run.sql(
        "SELECT r.state, c.code, coalesce(r.you_said, ''), coalesce(r.understood, ''),"
        " coalesce(r.real_world_declared, false), coalesce(r.recipient_id, 0),"
        " r.read_date IS NOT NULL, coalesce(r.invitation_id, 0)"
        " FROM linkup_reflet r LEFT JOIN linkup_category c ON c.id = r.category_id"
        f" WHERE r.id = {int(reflet_id)}"
    )[0]
    keys = (
        "state",
        "category",
        "you_said",
        "understood",
        "real_world",
        "recipient",
        "read",
        "invitation",
    )
    data = dict(zip(keys, row))
    data["real_world"] = data["real_world"] == "t"
    data["read"] = data["read"] == "t"
    data["recipient"] = int(data["recipient"])
    data["invitation"] = int(data["invitation"])
    return data


def mails_to(run, email):
    """``[{id, state, subject, body}]`` of the emails queued to
    ``email``, oldest first. The body is read in hexadecimal: the rows of
    ``run.sql`` hold one line each."""
    rows = run.sql(
        "SELECT m.id, m.state, coalesce(msg.subject, ''),"
        " encode(convert_to(coalesce(m.body_html, ''), 'UTF8'), 'hex')"
        " FROM mail_mail m LEFT JOIN mail_message msg ON msg.id = m.mail_message_id"
        f" WHERE m.email_to = {quote(email)} ORDER BY m.id"
    )
    return [
        {
            "id": int(mail_id),
            "state": state,
            "subject": subject,
            "body": bytes.fromhex(body).decode(),
        }
        for mail_id, state, subject, body in rows
    ]


def plain(body):
    """The text of an HTML body, its spacing collapsed."""
    text = html.unescape(re.sub(r"<[^>]+>", "", body))
    return re.sub(r"\s+", " ", text).strip()


def link_of(run, mail):
    """``(base, token)`` of the invitation link of a queued email."""
    match = re.search(LINK_RE, html.unescape(mail["body"]))
    run.check(
        match, f"courriel {mail['id']} : aucun lien /linkup/invite/<jeton>"
    )
    return match.group(1), match.group(2)


def user_by_login(run, login):
    rows = run.sql(
        f"SELECT id, karma FROM res_users WHERE login = {quote(login)}"
    )
    return (int(rows[0][0]), int(rows[0][1] or 0)) if rows else (None, None)


def link_state(run, uid_a, uid_b):
    rows = run.sql(
        "SELECT state, first_link_date IS NOT NULL FROM linkup_link"
        f" WHERE (user_a_id = {uid_a} AND user_b_id = {uid_b})"
        f" OR (user_a_id = {uid_b} AND user_b_id = {uid_a})"
    )
    return (rows[0][0], rows[0][1] == "t") if rows else (None, False)


def sam_draft_id(run):
    rows = run.sql(
        "SELECT r.id FROM linkup_reflet r JOIN res_users u ON u.id = r.author_id"
        " WHERE u.login = 'sam' AND r.state = 'draft'"
    )
    return int(rows[0][0]) if rows else None


def category_title(run, code):
    return run.sql(
        "SELECT reflet_title->>'fr_CA' FROM linkup_category"
        f" WHERE code = {quote(code)}"
    )[0][0]


# Browsers ------------------------------------------------------------


def private_window(run, key):
    """A browser logged in nowhere, kept under ``key`` among the personas
    so that a failure takes its screenshot too."""
    if key not in run.personas:
        run.personas[key] = Persona(run, key)
    return run.personas[key]


def skip_tour(persona):
    """Close the first-use tour bubble a new account gets, if it shows."""
    for _ in range(6):
        if persona.has(".o-linkup-Tour-skip"):
            persona.click(".o-linkup-Tour-skip")
            return
        time.sleep(0.5)


def is_focused(persona, css):
    return persona.js(
        "return !!document.activeElement && document.activeElement.matches(arguments[0]);",
        css,
    )


def check_box(persona, css):
    """Tick a checkbox, leaving it ticked when it already is."""
    box = persona.find(css)
    if not box.is_selected():
        persona.click(css)
    persona.wait_until(
        lambda d: persona.find(css).is_selected(), f"{css} coché"
    )


def newlink_contact(run, sam, email, name):
    """Step 1 of NewLink: the address and the name, then the card step."""
    open_reflet_view(sam)
    sam.close_notifications()
    sam.click(".o-linkup-RefletView-newlink")
    sam.find(f"{NEWLINK}[data-step='contact']")
    sam.wait_until(
        lambda d: is_focused(sam, ".o-linkup-Newlink-email"),
        "focus sur l'adresse",
    )
    sam.type(".o-linkup-Newlink-email", email)
    sam.type(".o-linkup-Newlink-name", name)
    sam.click(".o-linkup-Newlink-next", "Suivant : le reflet")
    sam.find(f"{NEWLINK}[data-step='reflet']")
    title = f"De quoi t'a parlé {name} lors de votre échange en personne ?"
    sam.find_text(f"{NEWLINK} p.fw-bold", title)


def newlink_card(run, sam, code, name, texts=True):
    """Step 2: the category, the two texts, the declaration of the
    exchange in person and the preview of the card; then on to the
    preview of the email. Return the card title."""
    title = category_title(run, code)
    sam.click(f"{NEWLINK} .o-linkup-HelpBar-category[data-code='{code}']")
    sam.find(f"{NEWLINK} .o-linkup-RefletForm-title svg[data-code='{code}']")
    sam.find_text(f"{NEWLINK} .o-linkup-RefletForm-title", title)
    if texts:
        sam.type(f"{NEWLINK} .o-linkup-RefletForm-youSaid", YOU_SAID)
        sam.type(f"{NEWLINK} .o-linkup-RefletForm-understood", UNDERSTOOD)
    sam.find_text(
        f"{NEWLINK} .o-linkup-RefletForm-realWorld",
        "Je confirme avoir eu cet échange en personne",
    )
    check_box(
        sam, f"{NEWLINK} .o-linkup-RefletForm-realWorld input[type='checkbox']"
    )
    toggle = sam.find(f"{NEWLINK} .o-linkup-RefletForm-previewButton")
    if toggle.get_attribute("aria-expanded") != "true":
        sam.click(f"{NEWLINK} .o-linkup-RefletForm-previewButton", "Aperçu")
    card = f"{NEWLINK} .o-linkup-RefletForm-preview .o-linkup-RefletCard"
    sam.find(f"{card} svg[data-code='{code}']")
    sam.find_text(f"{card} .o-linkup-RefletCard-title", title)
    sam.find_text(f"{card} .o-linkup-RefletCard-youSaid", YOU_SAID)
    sam.find_text(f"{card} .o-linkup-RefletCard-understood", UNDERSTOOD)
    sam.click(f"{NEWLINK} .o-linkup-RefletForm-send", "Suivant : l'aperçu")
    sam.find(f"{NEWLINK}[data-step='preview']")
    return title


def newlink_preview_and_send(run, sam, email, name):
    """Step 3: the preview of the email, which holds neither text; then
    send. Return the masked address shown."""
    _uid, _pid, sam_name = user(run, "sam")
    mail = sam.text(".o-linkup-Newlink-mail")
    run.check(
        email in mail, f"aperçu du courriel : destinataire {email} absent"
    )
    subject = MAIL_SUBJECT.format(name=sam_name)
    run.check(
        subject in mail,
        f"aperçu du courriel : objet « {subject} » absent : {mail!r}",
    )
    for text in (YOU_SAID, UNDERSTOOD):
        run.check(
            text not in mail,
            f"l'aperçu du courriel contient le texte du reflet « {text} »",
        )
    sam.find_text(".o-linkup-Newlink-noText", name)
    sam.click(".o-linkup-Newlink-send", "Envoyer l'invitation")
    sam.find(f"{NEWLINK}[data-step='sent']")
    shown = sam.text(".o-linkup-Newlink-sentTo")
    run.check("Invitation envoyée à" in shown, f"état après envoi : {shown!r}")
    run.check(
        masked(email) in shown,
        f"adresse affichée : {shown!r}, attendu {masked(email)}",
    )
    run.check(
        email not in shown, f"l'adresse en clair est affichée : {shown!r}"
    )
    return masked(email)


def send_invitation(run, case):
    """Sam invites the address of ``case`` from "+ NewLink", the three
    steps through the interface. Return the invitation row."""
    email, name, code = INVITED[case]
    sam = run.persona("sam")
    newlink_contact(run, sam, email, name)
    newlink_card(run, sam, code, name)
    newlink_preview_and_send(run, sam, email, name)
    invitation = invitation_of(run, email)
    run.check(
        invitation and invitation["state"] == "sent",
        f"invitation à {email} : {invitation}",
    )
    return invitation


def sign_up(run, persona, token, email, name):
    """Fill the signup form of an invitation page and send it; the
    password is random and stays in this process."""
    persona.goto(f"/linkup/invite/{token}")
    persona.find(f"{INVITE_PAGE} .o-linkup-InvitePage-form")
    persona.type("input[name='login']", email)
    persona.type("input[name='name']", name)
    password = secrets.token_urlsafe(18)
    persona.find("input[name='password']").send_keys(password)
    persona.find("input[name='confirm_password']").send_keys(password)
    persona.click(
        f"{INVITE_PAGE} button[type='submit']", "M'inscrire et lire le reflet"
    )
    persona.wait_webclient()


def invite_page_code(persona, token, suffix=""):
    persona.goto(f"/linkup/invite/{token}{suffix}")
    page = persona.find(INVITE_PAGE)
    return page.get_attribute("data-code") or "", page.text


# Steps ---------------------------------------------------------------


def n1(run):
    email, name, code = INVITED["signup"]
    sam = run.persona("sam")
    mails_before = len(mails_to(run, email))
    invitation = send_invitation(run, "signup")
    data = reflet(run, invitation["reflet_id"])
    expected = {
        "state": "pending_invite",
        "category": code,
        "you_said": YOU_SAID,
        "understood": UNDERSTOOD,
        "real_world": True,
        "recipient": 0,
    }
    got = {key: data[key] for key in expected}
    run.check(
        got == expected, f"reflet de l'invitation : {got}, attendu {expected}"
    )
    run.check(
        invitation["name"] == name, f"nom retenu : {invitation['name']!r}"
    )
    run.check(
        sam_draft_id(run) is None,
        "Sam garde un brouillon après l'envoi de l'invitation",
    )

    sam.find_text(
        ".o-linkup-RefletView-invitations h2", "Invitations en attente"
    )
    item = sam.find_text(".o-linkup-RefletView-invitation", name)
    run.check(
        "Invitation envoyée · reflet en attente" in item.text,
        f"entrée de l'invitation : {item.text!r}",
    )
    sam.find_text(".o-linkup-Newlink-resend", "Renvoyer le lien")
    sam.find_text(".o-linkup-Newlink-cancel", "Annuler l'invitation")
    # The entry of the list opens the invitation on its card.
    sam.click(".o-linkup-RefletView-invitation", name)
    card = sam.find(".o-linkup-Newlink-card")
    sam.find(f".o-linkup-Newlink-card svg[data-code='{code}']")
    for text in ("En attente d'inscription", YOU_SAID, UNDERSTOOD):
        run.check(
            text in card.text,
            f"carte de l'invitation sans « {text} » : {card.text!r}",
        )
    quota = re.sub(r"\s+", " ", sam.text(".o-linkup-Newlink-quota")).strip()
    run.check(
        quota == QUOTA_AFTER_FIRST,
        f"quota affiché : {quota!r}, attendu « {QUOTA_AFTER_FIRST} »",
    )
    mails = mails_to(run, email)
    run.check(
        len(mails) == mails_before + 1,
        f"courriels vers {email} : {len(mails)}, attendu {mails_before + 1}",
    )
    run.memory["n_invitation"] = invitation
    return f"invitation {invitation['id']} : {masked(email)}, reflet {invitation['reflet_id']} pending_invite ; {quota}"


def n2(run):
    email, name, _code = INVITED["signup"]
    _uid, _pid, sam_name = user(run, "sam")
    cron = run.sql(
        "SELECT c.active FROM ir_cron c JOIN ir_model_data d ON d.res_id = c.id"
        f" AND d.model = 'ir.cron' WHERE d.module = 'mail' AND d.name = {quote(MAIL_CRON)}"
    )
    run.check(
        cron and cron[0][0] == "f",
        f"file d'envoi des courriels active : {cron}",
    )
    mails = mails_to(run, email)
    run.check(
        len(mails) == 1, f"{len(mails)} courriel(s) vers {email}, attendu 1"
    )
    mail = mails[0]
    run.check(
        mail["state"] == "outgoing",
        f"courriel {mail['id']} à l'état {mail['state']}, attendu outgoing",
    )
    subject = MAIL_SUBJECT.format(name=sam_name)
    run.check(
        mail["subject"] == subject,
        f"objet : {mail['subject']!r}, attendu {subject!r}",
    )
    text = plain(mail["body"])
    for expected in MAIL_TEXTS:
        expected = expected.format(name=sam_name)
        run.check(expected in text, f"courriel sans « {expected} » : {text!r}")
    for forbidden in (YOU_SAID, UNDERSTOOD, name):
        run.check(
            forbidden not in text, f"le courriel contient « {forbidden} »"
        )
    base, token = link_of(run, mail)
    run.check(
        base == run.base_url,
        f"lien du courriel sur {base}, attendu {run.base_url}",
    )
    run.check(
        f"/linkup/invite/{token}/optout" in mail["body"],
        "lien de refus de toute invitation (…/optout) absent",
    )
    log_path = os.path.join(run.out_dir, "odoo.log")
    with open(log_path, encoding="utf-8", errors="replace") as fh:
        log = fh.read()
    run.check(token not in log, "le journal d'Odoo contient le jeton du lien")
    run.check(
        subject not in log, "le journal d'Odoo contient l'objet du courriel"
    )

    admin = run.persona("admin")
    admin.goto("/odoo/action-mail.action_view_mail_mail?debug=1")
    admin.find(".o_list_view")
    admin.type(".o_searchview_input", email)
    admin.keys(Keys.ENTER, css=".o_searchview_input")
    # The list has no recipient column: the facet filters on it, and
    # the single row left is the invitation.
    admin.find_text(".o_searchview_facet", email)
    admin.wait_until(
        lambda d: len(admin.finds(".o_list_view .o_data_row")) == 1,
        f"une seule ligne pour {email}",
    )
    row = admin.find(".o_list_view .o_data_row").text
    run.check(
        subject in row and "Sortant" in row,
        f"liste des courriels : ligne {row!r}",
    )
    run.memory["n_token"] = token
    return f"courriel {mail['id']} outgoing, en français, sans le texte du reflet ; lien et refus présents ; absent du journal"


def n3(run):
    email, name, _code = INVITED["signup"]
    token = run.memory["n_token"]
    invitation = run.memory["n_invitation"]
    sam_id, _pid, sam_name = user(run, "sam")
    guest = private_window(run, "prive_invite")
    code, text = invite_page_code(guest, token)
    run.check(code == "", f"page de l'invitation refusée : {code} {text!r}")
    intro = guest.text(".o-linkup-InvitePage-intro")
    run.check(
        intro == PAGE_INTRO.format(name=sam_name), f"présentation : {intro!r}"
    )
    page = guest.text(INVITE_PAGE)
    for forbidden in (YOU_SAID, UNDERSTOOD, name):
        run.check(
            forbidden not in page,
            f"la page de l'invitation contient « {forbidden} »",
        )

    sign_up(run, guest, token, email, SIGNUP_NAMES["signup"])
    guest.find(f"{VIEW} .o-linkup-RefletView-body")
    skip_tour(guest)
    new_id, _karma = user_by_login(run, email)
    run.check(new_id, f"aucun compte {email} créé")
    row = invitation_of(run, email)
    run.check(
        row["state"] == "accepted",
        f"invitation : {row['state']}, attendu accepted",
    )
    data = reflet(run, invitation["reflet_id"])
    run.check(
        (data["state"], data["recipient"], data["read"])
        == ("sent", new_id, False),
        f"reflet : {data['state']}, destinataire {data['recipient']}, lu {data['read']}",
    )
    state, _first = link_state(run, sam_id, new_id)
    run.check(
        state == "pending", f"lien Sam–invité : {state}, attendu pending"
    )
    contact = guest.find(f"{CONTACT}[data-user-id='{sam_id}']")
    unread = contact.find_elements(
        "css selector", ".o-linkup-RefletView-unread"
    )
    run.check(
        unread and unread[0].text.strip() == "Non lus : 1",
        f"Sam sans « Non lus : 1 » : {contact.text!r}",
    )

    guest.record_points()
    open_chat_with(guest, sam_id, sam_name)
    card = card_holding(guest, f"{RECEIVED}[data-state='sent']", UNDERSTOOD)
    click_in(guest, card, ".o-linkup-RefletActions-confirm")
    card_holding(guest, f"{RECEIVED}[data-state='confirmed']", UNDERSTOOD)
    run.check(
        reflet(run, invitation["reflet_id"])["state"] == "confirmed",
        "reflet non confirmé en base",
    )
    state, first = link_state(run, sam_id, new_id)
    run.check(
        (state, first) == ("active", True),
        f"lien après confirmation : {state}, premier lien {first}",
    )
    run.memory["n_new_user"] = new_id
    return f"compte {new_id} créé, reflet non lu, lien pending → active à la confirmation"


def n4a(run):
    token = run.memory["n_token"]
    guest = private_window(run, "prive")
    code, text = invite_page_code(guest, token)
    run.check(
        code == "linkup.invite_used",
        f"code de la page : {code!r}, attendu linkup.invite_used",
    )
    status = guest.text(".o-linkup-InvitePage-status")
    run.check(
        status == PAGE_USED, f"message : {status!r}, attendu « {PAGE_USED} »"
    )
    run.check(
        not guest.has(".o-linkup-InvitePage-form"),
        "formulaire d'inscription encore offert",
    )
    return f"« {status} »"


def n4b(run):
    email, name, code = INVITED["cancel"]
    sam = run.persona("sam")
    invitation = send_invitation(run, "cancel")
    sam.click(".o-linkup-Newlink-cancel", "Annuler l'invitation")
    sam.find_text(".o-linkup-Newlink-cancelled", CANCELLED_TEXT)
    row = invitation_of(run, email)
    run.check(
        row["state"] == "cancelled",
        f"invitation : {row['state']}, attendu cancelled",
    )
    data = reflet(run, invitation["reflet_id"])
    run.check(
        (data["state"], data["invitation"]) == ("draft", 0),
        f"reflet : {data['state']}, invitation {data['invitation']}, attendu brouillon sans invitation",
    )
    run.check(
        sam_draft_id(run) == invitation["reflet_id"],
        "le reflet n'est pas le brouillon de Sam",
    )
    run.check(
        not sam.has(".o-linkup-RefletView-invitation", name),
        "l'invitation annulée reste dans « Invitations en attente »",
    )
    sam.click(".o-linkup-Newlink-resume", "Reprendre le brouillon")
    sam.find(f"{VIEW} .o-linkup-RefletForm-title svg[data-code='{code}']")
    shown = sam.find(f"{VIEW} .o-linkup-RefletForm-youSaid").get_property(
        "value"
    )
    run.check(
        shown == YOU_SAID, f"brouillon repris : « Tu m'as dit » {shown!r}"
    )

    mails = mails_to(run, email)
    run.check(
        len(mails) == 1, f"{len(mails)} courriel(s) vers {email}, attendu 1"
    )
    _base, token = link_of(run, mails[0])
    guest = private_window(run, "prive")
    page_code, _text = invite_page_code(guest, token)
    status = guest.text(".o-linkup-InvitePage-status")
    run.check(
        (page_code, status) == ("linkup.invite_cancelled", PAGE_CANCELLED),
        f"lien annulé : {page_code!r} « {status} »",
    )
    run.memory["n_cancel_token"] = token
    return f"invitation {row['id']} annulée ; reflet {invitation['reflet_id']} redevenu brouillon ; lien : « {status} »"


def n4c(run):
    email, name, code = INVITED["cancel"]
    token = run.memory["n_cancel_token"]
    listed = "SELECT count(*) FROM linkup_email_blocklist WHERE reason = 'invite_optout'"
    before = int(run.sql(listed)[0][0])
    guest = private_window(run, "prive")
    page_code, text = invite_page_code(guest, token, "/optout")
    run.check(page_code == "", f"page de refus : {page_code!r} {text!r}")
    guest.find_text(
        ".o-linkup-InvitePage-optout",
        "LinkUp n'enverra plus aucune invitation",
    )
    guest.click(
        ".o-linkup-InvitePage-optout button[type='submit']",
        "Ne plus jamais recevoir d'invitation LinkUp",
    )
    status = guest.text(".o-linkup-InvitePage-status")
    run.check(
        status == PAGE_OPTOUT_DONE,
        f"refus : {status!r}, attendu « {PAGE_OPTOUT_DONE} »",
    )
    after = int(run.sql(listed)[0][0])
    run.check(after == before + 1, f"liste de refus : {before} → {after}")

    # The address now refuses every invitation: Sam sends the draft given
    # back to it again, sees the usual answer, and no email is queued.
    mails_before = len(mails_to(run, email))
    sam = run.persona("sam")
    newlink_contact(run, sam, email, name)
    newlink_card(run, sam, code, name, texts=False)
    newlink_preview_and_send(run, sam, email, name)
    row = invitation_of(run, email)
    run.check(row["state"] == "sent", f"nouvelle invitation : {row['state']}")
    mails = len(mails_to(run, email))
    run.check(
        mails == mails_before,
        f"courriels vers l'adresse refusée : {mails_before} → {mails}",
    )
    return f"« {status} » ; nouvelle invitation {row['id']} : Sam voit {masked(email)}, aucun courriel mis en file"


def n4d(run):
    email, _name, _code = INVITED["other"]
    sam_id, _pid, _sam_name = user(run, "sam")
    invitation = send_invitation(run, "other")
    mails = mails_to(run, email)
    run.check(
        len(mails) == 1, f"{len(mails)} courriel(s) vers {email}, attendu 1"
    )
    _base, token = link_of(run, mails[0])
    guest = private_window(run, "prive")
    sign_up(run, guest, token, OTHER_ADDRESS, SIGNUP_NAMES["other"])
    guest.find(f"{VIEW} .o-linkup-RefletView-body")
    skip_tour(guest)
    other_id, _karma = user_by_login(run, OTHER_ADDRESS)
    run.check(other_id, f"aucun compte {OTHER_ADDRESS} créé")
    row = invitation_of(run, email)
    run.check(
        row["state"] == "accepted",
        f"invitation : {row['state']}, attendu accepted",
    )
    data = reflet(run, invitation["reflet_id"])
    run.check(
        (data["state"], data["recipient"]) == ("expired", 0),
        f"reflet : {data['state']}, destinataire {data['recipient']}, attendu expired sans destinataire",
    )
    received = run.sql(
        f"SELECT count(*) FROM linkup_reflet WHERE recipient_id = {other_id}"
    )[0][0]
    run.check(
        received == "0",
        f"{received} reflet(s) reçu(s) par le compte {OTHER_ADDRESS}",
    )
    state, _first = link_state(run, sam_id, other_id)
    run.check(state is None, f"lien Sam–autre adresse : {state}")
    run.check(
        not guest.has(f"{CONTACT}[data-user-id='{sam_id}']"),
        "Sam figure parmi les contacts du compte inscrit avec une autre adresse",
    )
    return f"compte {other_id} créé ; invitation {row['id']} utilisée ; reflet {invitation['reflet_id']} expiré, sans destinataire"


def n5(run):
    new_id = run.memory["n_new_user"]
    guest = run.personas["prive_invite"]
    rows = run.sql(
        "SELECT r.code, l.points, coalesce(l.cap_reason, '') FROM linkup_points_ledger l"
        " JOIN linkup_points_rule r ON r.id = l.rule_id"
        f" WHERE l.user_id = {new_id} ORDER BY l.id"
    )
    run.check(rows, "aucune ligne de points pour le compte invité")
    bad = [row for row in rows if row[1] != "0" or row[2] != "new_account"]
    run.check(not bad, f"lignes payées ou hors « compte trop récent » : {bad}")
    _uid, karma = user_by_login(run, INVITED["signup"][0])
    run.check(karma == 0, f"karma du compte invité : {karma}")
    run.settle()
    bursts = guest.recorded_points()["bursts"]
    run.check(not bursts, f"points affichés au compte invité : {bursts}")
    lines = ", ".join(
        f"{code} {points} ({reason})" for code, points, reason in rows
    )

    # « Mes points » lists every line at 0, with the reason of the cap.
    guest.click(MENU_SECTION, "LinkUp")
    guest.click(MENU_ITEM, "Mes points")
    balance = guest.text(".o-linkup-MyPoints-balanceValue")
    run.check(
        re.sub(r"\D", "", balance) == "0",
        f"solde affiché : {balance!r}, attendu 0",
    )
    guest.wait_until(
        lambda _d: len(guest.finds(".o-linkup-MyPoints-line")) == len(rows),
        f"{len(rows)} ligne(s) dans l'historique de Mes points",
    )
    history = []
    for line in guest.finds(".o-linkup-MyPoints-line"):
        points = line.find_element(
            "css selector", ".o-linkup-MyPoints-linePoints"
        ).text.strip()
        reasons = line.find_elements(
            "css selector", ".o-linkup-MyPoints-lineReason"
        )
        reason = reasons[0].text.strip() if reasons else ""
        history.append((line.get_attribute("data-code"), points, reason))
    wrong = [
        entry
        for entry in history
        if re.sub(r"\D", "", entry[1]) != "0" or entry[2] != NEW_ACCOUNT_REASON
    ]
    run.check(
        not wrong,
        f"lignes de Mes points hors « 0, {NEW_ACCOUNT_REASON} » : {history}",
    )
    return f"{lines} ; aucune animation de points après {SETTLE} s ; Mes points : solde {balance}, historique {history}"


STEPS = [
    (
        "N1",
        "sam, + NewLink : adresse, nom, carte, échange en personne, aperçu, envoi ; i***@example.com, « Invitations en attente », « Renvoyer le lien », « Annuler l'invitation »",
        n1,
    ),
    (
        "N2",
        "Courriel resté en file (sortant) : générique, nom de l'inviteur, lien, 14 jours, refus de toute invitation, sans le texte du reflet, en français",
        n2,
    ),
    (
        "N3",
        "Lien en fenêtre privée : page qui nomme Sam sans le texte ; inscription avec l'adresse invitée → Vue Reflet, reflet non lu, lien pending ; confirmer crée le lien",
        n3,
    ),
    ("N4a", "Rouvrir le même lien : « invitation déjà utilisée »", n4a),
    (
        "N4b",
        "Seconde invitation puis « Annuler l'invitation » : le reflet redevient le brouillon de Sam",
        n4b,
    ),
    ("N4c", "Lien …/optout : l'adresse refuse toute invitation", n4c),
    (
        "N4d",
        "Inscription par un lien avec une autre adresse : le compte existe, le reflet n'arrive à personne",
        n4d,
    ),
    (
        "N5",
        "Compte créé par invitation (< 72 h) : lignes de points à 0 (« compte trop récent »), non affichées",
        n5,
    ),
]
