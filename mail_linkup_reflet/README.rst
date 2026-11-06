===============================
LinkUp — Reflections in Discuss
===============================

Core module of LinkUp: members of a dedicated instance exchange reflections
of real-life conversations inside the Discuss application.

* Three access levels in the ``LinkUp`` category: Member, Moderator and
  Administrator, each implying the previous one. A member is an internal user
  and holds no other right.
* A member sees the Discuss application only; the LinkUp entries are
  sub-menus of Discuss.
* A member's home action opens the Reflet view (``/odoo/linkup``), also
  reached from the LinkUp menu of Discuss.
* A member never holds the technical features group: the module moves its
  implication from the internal users to the system administrators, and the
  uninstall hook moves it back.
* The default ``general`` channel is restricted to system administrators, so
  a new member is subscribed to no channel.

Isolation
=========

Prototype of the member's reading scope over contacts and users
(``security/linkup_rules.xml``, ``tests/test_isolation.py``).

Covered:

* A member reads the ``res.partner`` of themself, of their companies and of
  the members of the channels they belong to, and the ``res.users`` of
  themself and of those channel peers. The scope follows channel membership
  without any cache to clear.
* The member rule on ``res.users`` is a group rule: Odoo joins it by AND with
  the global ``res_users_rule``, which narrows it without overriding
  ``_search`` or ``check_access``.
* LinkUp administrators and system administrators keep the native reading;
  internal users outside LinkUp are not affected.
* The people searches of Discuss run without ``sudo`` and stay in the scope:
  ``res.partner.im_search``, ``get_mention_suggestions``,
  ``get_mention_suggestions_from_channel``, ``search_for_channel_invite``
  (count included) and ``discuss.channel.get_mention_suggestions``.
* A member adds to a channel, a group or a chat only the partners already in
  their scope: ``add_members``, ``create_group``, ``channel_get`` and the
  creation of a channel refuse any other partner id, so an invitation cannot
  widen the scope.
* Discuss keeps working for a member: loading the messaging data, opening a
  channel and its member list, posting, fetching messages, opening a direct
  conversation with a channel peer.
* A direct conversation (``chat``) does not count as a shared channel: its
  two members read each other through another channel they share or
  through their link, so the chat that carries the reflections of a pair
  does not keep them open to each other.
* The two members of a ``linkup.link`` read each other while the link is
  ``pending`` (a reflection was sent) or ``active``; a ``closed`` or
  ``blocked`` link closes them again.
* A new channel created without an authorized group is kept to the LinkUp
  administrators (``_compute_group_public_id``, LU-F-063 RM2); an
  animation channel names its group, as ``channel_create`` does.

Not covered yet:

* A channel open to ``base.group_user`` or to the member group is readable
  by every member, and its member list and message authors are served
  through ``sudo``: a member sees its people without joining it, and joins
  it by themself.
* Moderators read like members; the moderation methods read the reported
  people through ``sudo``.
* Within the scope, ``login``, ``email`` and ``phone`` of other members stay
  readable, and the searches still match on email. Field ``groups=`` and the
  removal of the email search (LU-F-112 RM3, LU-NF-009) remain to do.
* The tours exercise the sending, the validation and the exact answer, a
  precision with its guess, and the strict start rule
  (``linkup_reflet_send_tour``, ``linkup_reflet_confirm_tour``,
  ``linkup_precision_send_tour``, ``linkup_precision_guess_tour``,
  ``linkup_strict_mode_tour``), the Reflet view
  (``linkup_reflet_view_tour``), a sending with the keyboard only
  (``linkup_keyboard_only_tour``), talking about oneself and ending the
  exchange (``linkup_talk_about_oneself_tour``,
  ``linkup_end_it_here_tour``), and "You add to my happiness" from a
  conversation and from the Reflet view (``linkup_happiness_send_tour``,
  ``linkup_happiness_receive_tour``).

Reflections
===========

* ``linkup.category``: the twelve categories of communication, as
  ``noupdate`` data (``data/linkup_category_data.xml``) with their French
  texts in ``i18n/fr_CA.po``. ``sequence`` orders the full band,
  ``reflet_bar_sequence`` the reduced bar; ``is_cnv`` marks the
  non-violent communication group. Members read them, LinkUp
  administrators edit them.
* ``linkup.reflet``: a member writes one draft (``action_save_draft``) and
  sends it (``action_send``) to a member of their scope; the recipient
  confirms, rejects, ignores or marks it inaccurate. Once confirmed, the
  pair takes turns through child reflections (exact answer, precision,
  continued reflection, talking about oneself, closing) chained by
  ``parent_id``; ``linkup.link.turn_reflet_id`` holds the current turn.
* Members have read access only, through record rules: the reflections they
  wrote, and those sent to them except while draft or once withdrawn. Every
  change goes through an ``action_*`` method, which checks the acting user,
  locks the row with ``FOR UPDATE NOWAIT`` and checks the state again; a
  concurrent call fails on the lock, and its retry by the RPC layer gets
  ``linkup.already_answered`` or ``linkup.expired``.
* Refusals raise ``LinkupError`` (``exceptions.py``), whose code reaches the
  client in ``error.data.context.linkup_code``; see "Error states".
* ``linkup.reflet.secret`` holds the hidden themes of a precision. No group
  has access to it; ``revealed_category_ids``, computed and not searchable,
  gives them to the author, and to both parties once the single guess is
  made.
* ``linkup.link``: one record per pair, stored ordered and unique, created
  ``pending`` by the first sending and ``active`` at the first confirmation.
  A ``pending`` link becomes ``closed`` once no initial reflection of the
  pair is still ``sent`` after a rejection, a withdrawal or an expiry; the
  next sending makes it ``pending`` again. An ``active`` or ``blocked``
  link never closes, and an inaccurate answer leaves the link ``pending``.
* A precision keeps its text as written: the server never inserts the
  starter of its hidden theme.
* ``_linkup_event(code, users, link, channel, key)`` is called with the
  scoring code of each event (``reflect_sent``, ``reflect_confirmed``,
  ``reflect_rejected``, ``reflect_withdrawn``, ``answer_exact``,
  ``precision_sent``, ``theme_guessed``, ``theme_missed``,
  ``continue_sent``, ``continue_confirmed``, ``close``,
  ``call_answered``). It does nothing here; ``key`` identifies an event
  that no reflection identifies alone, such as one answered call.
* A call of a direct conversation is answered when its second participant
  joins (``discuss.channel.member._rtc_join_call``); its two RTC sessions
  are then marked ``linkup_call_answered``, so joining the same call again
  answers nothing. Any answered call of an ``active`` pair reports
  ``call_answered`` for both, whoever started it (Q-42). While the turn of
  the pair is an exact answer, or a precision whose guess is made, the
  member whose turn it is holds the call buttons of "Talk about yourself";
  a call that this member started also ends that turn and takes the
  options off the card (LU-F-044). The caller is read from the server
  only. The first participant, and a call of a pair without an active
  link, report nothing.
* A daily cron expires the initial reflections left unanswered for
  ``linkup.reflet_expiry_days`` days (30 by default).
* Every sent reflection, initial or child, has a carrier message: a
  ``comment`` posted by its author in the direct conversation of the pair,
  kept on ``linkup.link.channel_id`` and opened by ``channel_get`` when
  missing. Its body is a neutral sentence in the recipient's language,
  without the texts or the themes; ``mail.message.linkup_reflet_id`` links
  it back. Opening the conversation and posting run inside
  ``authorization.linkup_post``, a ``ContextVar`` no client value reaches,
  which lets the author add the two parties to the chat and links the
  message in ``_message_post_after_hook``, before the broadcast.
* The card of a reflection (``linkup.reflet._to_store``) is the same for
  every reader: kind, state, sub-states, dates, texts, category by code,
  author and recipient partners, ``holds_turn``. It never holds the hidden
  themes nor ``recipient_ignored``; a withdrawn card loses its texts and its
  carrier body becomes "Reflection withdrawn.". The hidden themes reach the
  author on their own partner, both parties after the guess, and
  ``/discuss/channel/messages`` adds them for these readers only.
* Each transition sends the updated cards to the conversation over the bus;
  ignoring sends the ignore flag to the recipient alone.
* Demonstration data: eleven members, the links of Sam and France, and one
  reflection of Sam to France in each state, with its carrier messages.
* ``tools/linkup_recette.py`` creates a local acceptance database with the
  modules and their demonstration: new random passwords for its accounts,
  printed once, a LinkUp administrator, and the email queue cron archived
  so that no email leaves the machine.

Web client
==========

Sources in ``static/src/core/common``, loaded in ``web.assets_backend``.

* ``linkup.reflet`` and ``linkup.category`` are records of the mail Store
  (``linkup_reflet_model.js``, ``linkup_category_model.js``); the bus
  updates of the cards reach every view that shows them.
* A carrier message draws ``LinkupRefletCard`` instead of its body
  (``message_patch.xml``, ``message_model_patch.js``): category with its
  pictogram, "You told me" and "I understood that", the badge of the state
  and a sentence that depends on whether the reader wrote or received the
  reflection. A carrier is never empty nor editable: the server refuses
  its edition through ``/mail/message/update_content``, and any write of
  its content or deletion outside ``sudo``.
* A sent initial reflection records its reading by its recipient
  (``action_mark_read``), once, when its card is really seen: the tab is
  visible and at least half of the card, or of the screen, shows it
  (``linkup_read_watch.js``). A card drawn in a hidden tab records it when
  the tab comes back. From then on, its author can no longer withdraw it.
* The composer of a direct conversation of a member carries the Help bar,
  the categories of the reduced bar then all of them, and the form of the
  reflection with its preview, Cancel and Send (``reflet_composer.js``). The
  form works on the single draft of the member through
  ``action_save_draft``, ``action_send`` and ``action_discard_draft``; a
  refusal shows the message of its ``linkup_code``. When the window takes
  the focus back with nothing left to save, the form reads the draft of the
  server again, so the last save of two tabs wins. The tooltip of a
  category gives its short definition. The Write a reflection button next
  to the emojis shows or hides them.
* The card of a carrier message holds what its recipient can do
  (``reflet_actions.js``), each button calling the ``action_*`` method of
  the step:

  * a reflection waiting for its recipient: "That's a link!", "This
    exchange did not take place" after a confirmation dialog, "That is not
    what I said" with an optional correction, and "Ignore", which folds
    the card for the recipient only. The card takes the focus; ``→`` and
    ``←`` pressed on the card itself, not on one of its buttons, press the
    first two buttons, the keyboard counterpart of the swipes of the
    mobile application;
  * a confirmed or continued reflection, to the member whose turn it is:
    "Yes, that's exactly it!" with an optional word, or "I would like to
    clarify…", whose text starts empty and stays so when hidden themes are
    chosen in the full band, at most ``linkup_max_hidden_themes``;
  * a precision hiding a theme, to its recipient: a single guess in the
    full band; the themes reach the client of the recipient only with the
    result of the server;
  * an exact answer or a resolved precision, to the member whose turn it
    is (``holds_turn``): continue the reflection, whose category inserts
    its reformulation starter after "So if I understand correctly…"; talk
    about oneself, with the call and video buttons of Discuss first and
    the first-person starter of a category; or end it here, from the
    closing sentence, sent as empty when unchanged so that each reader
    sees it in their own language;
  * a disclosure, to its recipient: "Write a reflection", a continued
    reflection prefilled with the starter of its category.

  No points are shown. ``Escape`` closes an open form; the category band
  is a toolbar, walked with the arrow keys. After an action the client
  reads the cards and the new messages of the conversation again, which
  the bus also brings.
* The LinkUp panel, a thread action of a direct conversation, gives the
  state of the link and the history of the pair
  (``linkup.reflet.linkup_history``, LU-F-018): the reflections sent and
  received, the most recent first, filtered by visible category and by
  state. A hidden theme is never a visible category, so a precision whose
  theme is still to guess matches none of its themes.
* The author of a sent initial reflection that its recipient has not read
  withdraws it from its card (LU-F-019), after a confirmation. The Reflet
  view keeps the reflections of the member still waiting for their
  recipient (``sent_ids``), each with that button; a phantom one shows
  there as delivered.
* The Reflet view, client action ``linkup.reflet_view``
  (``static/src/views/reflet_view``): the member, the Help bar, the zone of
  the card and the column of the contacts. The form of the card is the one
  of the composer (``reflet_form.js``), on the same single draft. Choosing a
  category opens the card with the focus in its first empty text, choosing
  a contact makes it the recipient, and dropping a category on a contact
  (``useDraggable``) does both. Without a pointer: the Help bar is a
  toolbar, each contact a button, and "Send to…" opens the list of the
  contacts, walked with the arrow keys, where ``Enter`` chooses the
  recipient and sends and ``Escape`` closes; a field left to fill, such as
  the declaration of the exchange in person that the contact requires,
  then takes the focus. Once sent, the focus reaches the link of the
  reflection, which opens the direct conversation in Discuss, as each
  contact does.
* ``linkup.reflet.linkup_reflet_view_info`` gives the contacts and the
  draft. The contacts are the LinkUp members of the scope: the members of
  the groups and channels of the member, the other party of an ``active``
  link, and that of a ``pending`` link in which the member received a
  reflection; a ``pending`` link opened alone adds nobody and a ``blocked``
  one removes the other member. Those holding an unread initial reflection
  sent to the member come first, labelled, then the most recent
  interaction of the pair, then the name.
* ``linkup.reflet.linkup_channel_info`` gives the client the recipient, the
  link, the draft and the recent cards of a conversation;
  ``res.users._init_store_data`` sets ``linkup_is_member`` and
  ``linkup_max_hidden_themes``.
* Pictograms are inline SVG drawn with ``currentColor``; colours come from
  the variables of web and Bootstrap, with ``linkup.dark.scss`` in the dark
  bundle. Texts go through ``_t`` and ``i18n/fr_CA.po``.
* Hoot tests in ``static/tests`` run in the browser through
  ``tests/test_ui.py`` (``TestLinkupRefletHoot``), or by hand at
  ``/web/tests?preset=desktop`` filtered on ``@mail_linkup_reflet``.

Start rule
==========

* ``linkup.start_rule_mode``, set in the LinkUp block of the general
  settings: ``strict`` (default), ``incitative`` or ``off``.
  ``discuss.channel.linkup_start_rule``, written by LinkUp administrators
  only, is ``inherit`` or one of these modes: a direct conversation inherits
  the global mode, the thread of a channel follows its channel, a group or
  a channel has no rule unless one is set.
* The rule binds the restricted members. A direct conversation opens once
  the link of its two members is ``active``, or when one party is not a
  restricted member; a group or a channel in ``strict`` opens to a member
  who has an active link with another of its members.
* In ``strict`` mode, until then, ``discuss.channel.message_post`` refuses
  every post of a member with ``linkup.start_rule``, whatever its type,
  attachments, voice messages and replies included, except the carrier
  message of a reflection of the conversation (``authorization.linkup_post``)
  and a ``notification`` whose text the server writes: under ``sudo``, or
  inside ``authorization.server_notification`` (the pin of a message, the
  arrival of a member). The full composer, a scheduled message or the
  feedback of an activity therefore post nothing there. Joining a call,
  adding a reaction and editing an earlier comment are refused too.
* Nothing a client sends goes around it: ``message_post`` and
  ``message_post_with_source`` of a conversation are not callable remotely
  (``api.private``); ``/mail/message/post`` takes neither ``message_type``
  nor ``subtype_xmlid`` from a member, so it posts a ``comment``, and drops
  the ``linkup`` keys of the context it receives; outside ``sudo``, a member
  creates the message of a conversation only from within ``message_post``
  (``authorization.channel_post``) and rewrites none.
* The context of a call is the client's own, whichever way it comes
  (``call_kw``, ``/jsonrpc``, the ``context`` of a JSON route). Every public
  method of LinkUp runs with its language, time zone and companies only
  (``client_context.server_context``): ``active_test`` turned off lets no
  archived account, conversation or rule in, and no key of a module
  changes what the method does. The records the server writes
  (``linkup.server.record``: reflections, links, highlights, blocks,
  reports, invitations, the ledger, the consents, the audit log) take the
  defaults of their fields only, never a ``default_<field>`` of the
  context, whichever path creates them.
* ``_channel_basic_info`` gives the client ``linkup_start_rule`` and
  ``linkup_start_rule_satisfied``, sent again to the conversation when its
  link becomes active. The composer of Discuss and of the chat windows then
  shows, in ``strict`` mode, a banner in place of the text field, with
  "Make a reflection" in a direct conversation, which opens the Help bar
  and gives it the focus; in ``incitative`` mode, the banner sits above a
  usable composer.
* Contact is initiated by the server (LU-F-063 RM1): a member creates the
  direct conversation of a pair with an ``active`` link only
  (``channel_get``, which the chat windows, the avatar cards and the
  "Start a conversation" field of Discuss call), and opens again one they
  already belong to; the server opens the others to carry a reflection,
  inside ``authorization.linkup_post``. Every refusal is the same
  ``AccessError``. The Reflet view offers to open the conversation of a
  contact only when it exists or the link is active. A group, which has no
  rule by default, takes from a member only the people of an ``active``
  link (``create_group``, ``add_members``, ORM), and only a LinkUp
  administrator creates a channel or changes the type of a conversation.
  A member changes neither the name nor the description of a direct
  conversation, and those of a group or a channel under the start rule
  only.

Blocking, suspension and reports
================================

* ``linkup.block`` (LU-F-115): ``action_block`` and ``action_unblock``, by
  user or partner id, force the blocker to the current user; a member
  blocks a member they read, share a link with, or already block, and any
  other id gets the same ``linkup.unavailable``. Members read their own
  blocks, moderators and administrators those of the others too, never one
  held on themselves; nobody writes one directly. ``linkup_blocked_members`` lists those of the member.
* A block in either direction makes the link ``blocked``, which closes the
  scope of the pair and removes each one from the contacts of the other.
  Lifting the last block gives it back ``active``, ``pending`` or
  ``closed`` from its reflections. ``linkup.link.state`` is kept to LinkUp
  administrators, and the clients read a ``blocked`` link as ``closed``.
* In a ``blocked`` pair: no exchange of a reflection (confirmation,
  answers, guess, options) and no post, reaction or call in the direct
  conversation, all refused with ``linkup.unavailable`` "This conversation
  is unavailable."; reading, ignoring and withdrawing stay possible. In a
  shared conversation, a mention and ``@everyone`` skip the other party, a
  call never rings for them, and a reaction to their messages is refused.
* The blocked member is not told. A reflection they send to the blocker is
  a phantom (``linkup.reflet.phantom``, kept to system administrators): it
  is ``sent`` for its author, has no carrier message, gives no scoring
  event, sends nothing on the bus to the recipient, whom the record rules
  and the actions treat as a stranger to it, and expires as usual. A
  highlight to the blocker is a phantom too (``linkup.highlight.phantom``):
  its sender reads it and sees it go out as any other, its recipient never
  reads it; once the block is lifted, a new press replaces it with a
  delivered one. The member who blocks sends neither to the member they
  block.
* The blocked member reads the direct conversation of the pair as that of
  a deleted account: ``linkup_channel_info`` and ``linkup_history`` answer
  ``{"available": False}``, since an active link that reads closed would
  tell the block. Neither party types in it (``_notify_typing``), and an
  edition adds no mention of a member a block separates from the author.
* Blocking withdraws the highlight the blocker sent and hides the one they
  received, and unpins the direct conversation for the blocker only.
* ``mail`` lets any internal user write to any partner id without a
  conversation: a message without a document and its inbox notification,
  ``message_notify``, the recipients or the stars of a message. Outside
  ``sudo``, a restricted member creates a ``mail.message`` only through the
  ``message_post`` of a conversation, writes neither the recipients, the
  notifications nor the stars of a message, and creates no
  ``mail.notification``: nothing reaches a person past the start rule, a
  block or a suspension.
* ``res.users.linkup_suspended_until`` is read and written by LinkUp
  administrators only, through ``action_linkup_suspend`` and
  ``action_linkup_lift_suspension``. Until that date, a restricted member
  sends no reflection, post, reaction, highlight or call, adds nobody to a
  conversation, answers no reflection and receives none; reading,
  withdrawing, blocking and reporting stay possible.
* ``linkup.report`` (minimal, LU-F-114 RM6): ``action_create_report``
  reports one reflection, message or member that the reporter reads with
  their own rights; it forces the reporter, derives the reported member,
  sets ``urgent`` for a threat, a minor in danger or a person in distress,
  and ignores every other value. The same open report for the same reason
  is returned again; beyond ``linkup.max_reports_per_day`` (20) a day, the
  code is ``linkup.rate_limited``. A member reports a member they read or
  share a link with, so that both parties of a block still report each
  other. Members read the reports they made; moderators the others, except
  those in a conflict of interest with them
  (``linkup_moderator_conflict``: made by them, about them, or whose
  reporter or reported member shares a link with them), and write only
  their processing (state, moderator, action, note); administrators
  manage them all, those in a conflict of interest with them excepted,
  which they neither read, process nor delete.
* A rejection checks the author (LU-F-023 RM5): beyond
  ``linkup.rejection_alert_count`` (5) recipients within
  ``linkup.rejection_alert_days`` (30), counting only accounts of at least
  seven days and one recipient per group of actively linked recipients,
  the server creates one ``repeated_rejections`` report while it is open.
  It sanctions nobody.
* The web client: a received card holds "Report this reflection" (a reason
  and an optional comment) and "Block", which asks for a confirmation
  listing what a block does; the LinkUp panel blocks or unblocks the other
  member; the help page lists the blocked members, each with "Unblock".

Not covered yet:

* The ORM still tells the author of a phantom reflection that it has no
  carrier message, and its answer comes quicker, without one; a reflection
  composed from a conversation the author shares with the blocker shows no
  card there. The Reflet view lists it among the reflections waiting.
* A member out of the scope reads ``linkup.unavailable`` for a reflection
  sent to a closed link, and a phantom delivery for a member who blocks
  them.
* The moderation console, the notification of the moderators for an urgent
  report and the report of a message from its menu belong to
  ``mail_linkup_community``.

NewLink invitations
===================

* ``linkup.reflet.action_send(invite={"email": …, "name": …})`` sends the
  draft to a person who may not be a member (LU-F-020): the reflection
  waits in the ``pending_invite`` state on a ``linkup.invitation``. The
  address is required and normalized, the name is seen by the inviter
  only, the declaration of an exchange in person is required, and the
  invitation by phone is refused until its lot.
* The token of an invitation is 256 random bits; only its SHA-256 is
  stored, kept to the system administrators. The link
  ``/linkup/invite/<token>`` lasts ``linkup.invitation_expiry_days`` (14)
  days. A member sends at most ``linkup.max_invitations_per_day`` (10) a
  day, new ones and links sent again, then gets ``linkup.rate_limited``.
* The email (``mail_template_linkup_invitation``) is generic: the name of
  the inviter, the link, its validity, the privacy policy when
  ``linkup.privacy_policy_url`` is set, the refusal of every invitation
  and the page in the other language; never the texts. It is rendered in
  the language of the inviter, attached to no record and created by the
  superuser: the inviter reads its message neither by search nor by id,
  so that nothing tells them whether it went out, nor gives them the
  token. An address that receives no email costs the same rendering.
* The inviter always gets the same answer, the masked address
  (``c***@example.com``) and the card: for an unknown address, for the
  address of a member, for an address of the refusal list and for the
  address of a member a block separates from them. The email goes out to
  the unknown address only; it is rendered and dropped otherwise. No link
  nor conversation exists before the invitation is used.
* The address of a member gets no email (RM6): the invitation reaches the
  member inside LinkUp (``invitee_id``, kept to the LinkUp administrators),
  over the bus as ``linkup.invitation/received`` and in "Reflections
  received by invitation" of the Reflet view, with the card.
  ``action_accept_received`` delivers the reflection and confirms it at
  once, which makes the link ``active``; ``action_ignore_received`` sets
  it aside, without telling the inviter, until it expires. A member who
  blocks the inviter, or is suspended, receives nothing, and
  ``res.users._linkup_accepts_invitation`` lets another module restrict
  who reaches a member.
* When the invited address uses the invitation, by the signup, the link or
  the Reflet view, the inviter receives ``linkup.invitation/accepted``
  with the name of the new contact, announced by their client unless
  ``linkup_notify_invitation_accepted`` is off. A link used with another
  address tells them nothing.
* The page of the link names the inviter, never the texts, and holds the
  signup form of ``auth_signup``, whatever ``auth_signup.invitation_scope``
  says. The account copies ``user_linkup_member_template``, inactive: an
  internal user of the member group, whose home action is the Reflet view.
  The signup uses the token once. With the invited address, the reflection
  reaches the new member as from ``action_send``: link ``pending``, carrier
  message in the direct conversation, unread in the Reflet view. With
  another address, as for a forwarded link, the account exists but the
  reflection expires and reaches nobody.
* The pages of the link send no referrer and are not cached: their URL
  holds the token.
* A logged-in member who holds the invited address uses the link for
  their account; another member reads that the invitation is not theirs,
  and it stays usable. A used, cancelled, expired or unknown link gets a
  page that says so (``linkup.invite_used``, ``linkup.invite_cancelled``,
  ``linkup.invite_expired``), with the native signup and login.
* ``/linkup/invite/<token>/optout`` asks, then lists the address in
  ``linkup.email.blocklist`` (``invite_optout``), as an HMAC keyed by the
  secret of the database, for 24 months; the list is checked before each
  email. Only LinkUp administrators read it.
* ``action_cancel`` (LU-F-026 RM2) voids the link and gives the reflection
  back as the draft of the inviter, who sends or deletes another draft
  first; ``action_resend`` sends the link again with a new token, the
  former one void, without moving the expiry. A suspended member neither
  invites nor sends a link again. Members read their own
  invitations and write none; the account that used one is kept to the
  LinkUp administrators.
* A daily cron expires the invitations past their date with their
  reflection, then deletes them one day after the expiry (LU-NF-015),
  with their reflection when nobody received it, and the expired entries
  of the blocklist. The reflection that a link used with another address
  let expire is deleted one day after that use.
* The web client: "+ NewLink" in the contacts of the Reflet view, and in
  the LinkUp section of Discuss, which opens the view on it, goes through
  the steps of the mock-up: the address and the name, the card of the
  same single draft, the preview of the email with the sendings of the
  day, then the invitation sent with "Send the link again" and "Cancel the
  invitation". Dropping a category on "+ NewLink" opens it on that card.
  "Pending invitations" lists those still waiting under the contacts.

Not covered yet:

* The invitation by phone and its share link, the verification of the
  email of a public signup, the consents and the anti-robot limits of a
  signup belong to ``mail_linkup_community``; without it, the signup
  through an invitation needs no other check than the token.

You add to my happiness
=======================

* ``linkup.highlight`` puts a member in the light of another one, without
  points. ``action_send`` forces the sender to the current user, accepts
  a person of their scope only, and keeps at most one active highlight per
  pair and direction (a partial unique index); a new press returns the
  active one. In a ``blocked`` pair, the blocked member sends a phantom
  highlight, which only they read, and the one who blocks is refused.
* The next exchange of the pair puts it out: the carrier of a reflection
  in their direct conversation, a comment of the highlighted member there,
  a call started or joined in it. The highlighted member hides it
  (``action_dismiss``), the sender withdraws it (``action_withdraw``).
* Members read the highlights they sent or received and write none; a
  LinkUp administrator manages them all. Each change reaches both parties
  over the bus; the recipient gets ``linkup.highlight/received``.
* The LinkUp panel of a direct conversation asks before putting the other
  member in the light, then offers to withdraw it, and shows the highlight
  received with "Hide". The Reflet view rings the avatar of the member
  with a halo and the avatars of up to three senders, and rings each
  sender in the contacts.
* The happiness field of the Reflet view (LU-F-051) puts a contact in the
  light when dropped onto them, or, without a pointer, from the list it
  opens, walked with the arrow keys. A contact the member puts in the light
  carries a sun.

Sounds and notifications
========================

* Five sounds join the service ``mail.sound_effects``: ``linkup-sent``,
  ``linkup-received``, ``linkup-success``, ``linkup-yeah`` and
  ``linkup-ting``. They are synthesized by ``tools/generate_sounds.py``
  from sine tones, with no third-party recording, and share the licence
  of the module; the script rebuilds the same files.
* ``res.users.settings`` holds the choices of each member:
  ``linkup_sound_enabled`` (sent and received, on by default),
  ``linkup_reward_sounds_enabled`` (off by default) and one switch per
  notification (``linkup_notify_reflet_received``,
  ``linkup_notify_confirmed``, ``linkup_notify_highlight``). The help page
  writes them. A sound always comes with a visible change.
* A received reflection replaces the sound of Discuss with the LinkUp one
  and follows the mute of Discuss; the web push leaves out the members who
  turned its notification off. A confirmed reflection and a received
  highlight show a notification of the browser where the member allowed
  them, and a notification of Odoo otherwise; both follow the mute of
  Discuss.
* ``linkup_notify_discreet`` (LU-F-092 RM4, off by default) makes every
  LinkUp notification read "LinkUp", "New LinkUp event", without a name nor
  an avatar: in the browser, and in the web push of a reflection, which is
  then built apart in the language of each such recipient.
* ``linkup-yeah`` is registered with the others but played by nothing
  here: it comes with the points of a sending, which the scoring module
  shows.

Help and first-use tour
=======================

* The round "?" button of the Help bar, of a received card and of the
  guess turns the guide mode on (``aria-pressed``). Every element marked
  ``data-linkup-guide`` then carries a number, and activating it opens its
  sheet instead of acting: "Guide · n of N", the definition, what to say
  and not to say and the starter of a category (from ``linkup.category``,
  translatable), and what a press does in this context. ‹ › move, "Show"
  leaves the guide and puts the screen in the state described, ``Escape``
  or a second press on "?" leaves it. In the Reflet view, the guide closes
  the list of "Send to…", whose ``Enter`` would send.
* The client action ``linkup.help`` lists the twelve categories, the
  sounds and notifications of the member and "Replay the tour". The user
  menu and the LinkUp menu of Discuss open it.
* The first-use tour has five steps (LinkUp section, Help bar, free text in
  strict or incentive mode, LinkUp panel, "?"), registered in
  ``web_tour.tours``. The tour service of Odoo starts a tour by itself only
  for a user with ``tour_enabled`` and from a ``web_tour.tour`` record, so
  the module shows the steps in its own bubble ("Next", "Skip the tour"),
  started when Discuss opens. ``res.users.linkup_tour_done`` records that
  the member finished or skipped it, on every device; the clients of the
  member already open receive it over the bus. The settings hold
  the global switch (``linkup.first_use_tour``) and "Reset for all
  members", reserved to a LinkUp administrator.

Error states
============

* ``exceptions.LINKUP_ERROR_CODES`` is the catalogue of §9.8, and the only
  codes a ``LinkupError`` takes: any other one raises ``ValueError``.
  ``linkup.cap_reached``, ``linkup.not_verified`` and
  ``linkup.consent_required`` belong to the scoring module and to the
  public signup; the client already explains the last two.
* ``linkup_errors.js`` gives the message of each code, and of three codes
  of the client: ``network`` (the request got no answer), ``session``
  (``odoo.http.SessionExpiredException``) and ``media_denied`` (the
  browser refuses the microphone or the camera). ``LinkupErrorAlert``
  shows it, with "Try again" after a lost connection, which runs the
  action again, and "Log in" after an expired session; the draft of a
  reflection stays on the server.
* A refused action on a card reads the card again: a reflection withdrawn
  or expired in the meantime turns grey and loses its buttons, one
  answered elsewhere shows its new state, and the message stays.
* A call from "Talking about oneself" is not started while the browser
  refuses the microphone, or the camera for a video call, as the
  Permissions API tells it.

Settings menu
=============

* The avatar of the member in the Reflet view opens, by a double click or
  through "My profile", the menu of LU-F-080 in its order: Help, Email,
  Phone, Photo, Sounds and notifications, Privacy, My data, Blocked
  members. Help opens the LinkUp help, and Sounds and notifications and
  Blocked members open it on their section (action context
  ``linkup_section``). Email and Photo open the preferences of the user.
* Phone, Privacy and My data have no screen in this module: they are
  disabled and say which feature brings them (the profile of the member,
  the export and the deletion of the data).
* A module that brings a screen adds its entry after these eight, by
  patching ``LinkupProfileMenu.entries`` with an entry whose ``action``
  is what choosing it opens; the keyboard and the roles are those of the
  other entries.

Status
======

Access skeleton, the data and models of the reflections, their carrier
messages, Store and bus, the card with its answers (validation, exact
answer, precision, guess, follow-up options), the composer and the LinkUp
panel, the start rule, the Reflet view, "You add to my happiness", the
sounds and notifications, the guide and the first-use tour, blocking,
suspension, minimal reports, the contact initiated by the server, and the
NewLink invitations by email with the signup through their link, the
withdrawal from the client, the history of a pair, dragging the happiness
field onto a person, the settings menu of the avatar, discreet
notifications, and the error catalogue with its states.

License
=======

AGPL-3.0 or later.
