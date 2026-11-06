==================
LinkUp — Live chat
==================

Extends ``im_livechat`` with the LinkUp rules, in four roles:

* the website widget welcomes visitors without an account (LU-F-124);
* a chatbot guides a first reflection step by step (LU-F-125);
* a distress opens a conversation with an available moderator (LU-F-126);
* a member operator and a visitor exchange reflections in the widget
  (LU-F-127).

A visitor is a ``mail.guest``: the cookie of the widget names it, never a
parameter of a request.

Channels
========

The data holds two ``im_livechat.channel``, marked by ``linkup_kind``:

* "LinkUp welcome" (``welcome``): its operators are the members who
  volunteer, added by a LinkUp administrator in Live Chat › Channels; its
  rule shows the welcome chatbot on every page of the website, whose
  live chat channel it is.
* "LinkUp distress" (``distress``): no rule, no operator of its own. Its
  operators are the LinkUp moderators, and only the server opens its
  conversations.

``linkup_start_rule`` of a channel sets the start rule of its
conversations: the global rule of the LinkUp settings by default, ``off``
on the distress channel.

Welcome of the visitors
=======================

The welcome script offers: discover LinkUp, sign up (``/web/signup``), "I
received an invitation", a first reflection, talk to a member, need help
now. No step waits for a typed address, phone or token: the answer about an
invitation is the same text for every visitor, and points to the link of
the email.

A signup made in the browser of a visitor who talked in a live chat
conversation of LinkUp remembers that visitor on the account. Once the address is
verified (``/linkup/verify``), the draft of the visitor becomes the draft
of the member, unless the member already holds one, the reflections of the
visitor become theirs, and the scoring events held for the visitor are
paid. Before, nothing is given.

A logged-in user gets no welcome session: ``/im_livechat/init`` answers
``linkup_redirect`` with Discuss, and ``/im_livechat/get_session`` opens
nothing. A visitor opens at most ``linkup.livechat_sessions_per_ip_hour``
welcome sessions an hour from one address (20).

Reflection guide
================

``chatbot.script.step.step_type`` gains ``linkup_category``,
``linkup_you_said``, ``linkup_understood``, ``linkup_reflet_review`` and
``linkup_forward_moderator``.

* The answers of a ``linkup_category`` step are the active categories,
  kept in step with them, in every installed language; the step lists
  each category with its definition.
* "You told me" shows the category chosen and its examples; "I understood
  that" its starter; the review shows the draft.
* ``_process_answer`` writes each answer into the single draft of the
  party, before the next step is fetched: ``action_save_draft`` for a
  member, the draft of the ``mail.guest`` for a visitor. The checks of the
  core apply on the server: a category to choose, a text required and not
  longer than ``linkup.reflet_text_max_length``. A refused answer raises
  ``linkup.validation`` and the step stays the current one.
* The chatbot never sends. "Restart" keeps the draft; choosing another
  category keeps the texts. ``/chatbot/restart`` restarts the script of a
  LinkUp conversation only while its party holds it alone with the
  chatbot: once a member or a moderator joined, or on the distress
  channel, it reads ``linkup.unavailable``.
* A member opens the guide by ``linkup.reflet.linkup_start_guide``, a
  conversation with the chatbot alone; a visitor by the welcome script.

Distress
========

A report of distress (``/linkup/v1/report``, ``reason = distress``), or
"Need help now" of the welcome script for a visitor, first creates the
urgent report, then opens, on the server, a conversation of the distress
channel with an available moderator.

* The moderators in a conflict of interest with the report (its reporter,
  the reported member, a member linked to one of them) are never chosen:
  ``authorization.distress_opening`` opens the distress channel, for the
  time of the choice, to the others only. A ``previous_operator_id`` that
  names an excluded moderator is ignored.
* Without a moderator online, no conversation opens: the reporter reads
  the help resources (``linkup.help_resources``, or 9-8-8 and 9-1-1) and
  the delay of an urgent report, which waits in the queue.
* "Need help now" brings a moderator into a welcome conversation that
  its party holds alone with the chatbot only; in one a member already
  operates, the report waits and the resources are posted. Once a
  moderator joined, ``/chatbot/step/trigger`` ends the script there, so
  the widget triggers no further step that would close the conversation.
* The conversation has no start rule, reminds that LinkUp is not an
  emergency service, and its opening is written to the audit log of the
  report (``distress_open``).
* Outside the opening by the server, the distress channel has no
  operator: ``/im_livechat/get_session`` (and its CORS route) opens
  nothing there, whatever the client sends; ``/im_livechat/init`` offers
  nothing; its page and its loader do not exist. Two global record rules
  keep a distress conversation, its members and its messages to its two
  parties: no live chat manager, moderator or other visitor reads or
  finds it.

Reflections with a visitor
==========================

``linkup.reflet`` gains ``author_guest_id`` and ``recipient_guest_id``:
each party is a member or a visitor, never both. A reflection of a live
chat conversation lives in it, without a link, and has no hidden theme.

* The routes of a visitor, ``/linkup/v1/livechat/reflet/info``,
  ``/draft``, ``/send``, ``/confirm`` and ``/reject`` (``auth='public'``),
  act only in a welcome conversation the visitor belongs to; any other
  case gets ``linkup.unavailable``. A member logged in reaches the same
  routes as themself, as the widget and Discuss do; the ORM methods
  ``linkup_livechat_info``, ``action_livechat_send``,
  ``action_livechat_confirm`` and ``action_livechat_reject`` serve them
  too.
* The information of a live chat conversation of LinkUp gives the role of
  its channel (``linkup_livechat_kind``) and whether a reflection may go
  between its visitor and its member (``linkup_can_reflect``); its start
  rule reads as satisfied while it does not bind yet. All three reach both
  parties again when a member or a moderator joins.
* The actions take the locks of the core: the party whose step it is, the
  row locked and its state checked again, a member neither suspended nor
  unverified. The carrier message is posted in the conversation by its
  author, who reads the member by their pseudonym of the live chat.
* Such a reflection has no link: the actions of the core on it (confirm,
  reject, withdraw, answer) read ``linkup.unavailable``, and its recipient
  only reads, ignores or erases it there. Once its visitor signed up, its
  answer through the live chat reads ``linkup.unavailable`` too.
* The start rule binds a live chat conversation once it holds two people:
  in ``strict``, the free text of the visitor and of the operator is
  refused with ``linkup.start_rule`` until a reflection of the
  conversation is confirmed; in ``incitative`` it passes with the banner.
  The answers to the chatbot before a member joins, the messages of the
  chatbot and the carrier messages pass.
* The operator reports the visitor
  (``linkup.report.action_report_livechat_visitor``): the report carries
  the conversation, the visitor (``reported_guest_id``) and their last
  message.
* A reflection of a live chat left unanswered expires after
  ``linkup.reflet_expiry_days`` days, as a reflection of the core.

Points of a visitor
===================

A visitor has no account, so neither ledger line nor karma. Each scoring
event of a reflection with a visitor waits in ``linkup.guest.event``
(Q-43), keyed as the ledger keys it (``reflet:<id>``), once. A pair of a
visitor and a member has no link, whose caps the ledger counts: a
confirmation is keyed by the pair (``livechat:<visitor>:<member>``), and
pays once per pair, as the first link of two members does. At the
verified signup of the visitor, the events are reported to the scale with
their keys: both parties earn their points at that moment, the member
operator included, and a second report pays nothing. An event still
waiting after ``linkup.guest_event_expiry_days`` days (30) is deleted
without points by a daily cron.

Widget of the visitors
======================

The widget of ``website_livechat`` loads, in ``im_livechat.assets_embed_core``,
the card, the form, the Help bar and the guide mode of
``mail_linkup_reflet``, file by file, and "Need help now" of
``mail_linkup_community``. The views of a member (panel, profile menu,
first-use tour) stay out of it, and so do their stylesheets, which read
variables of the web client only: ``static/src/embed/linkup_widget.scss``
styles the widget with the variables of Bootstrap and of ``web``. The
widget keeps the light theme (LU-NF-054): no ``*.dark.scss``.

* The steps ``linkup_category``, ``linkup_you_said`` and
  ``linkup_understood`` wait for an answer (``ChatbotStep.expectAnswer``).
  The categories are buttons with their icon, the other answers buttons
  too, reached with the keyboard; the composer names the text a step asks
  for. An answer the server refuses keeps its step, and its message shows
  in an alert above the composer.
* A polite live region, outside the screen, reads each new message of the
  chatbot or of the other person.
* Once a member joined, the start rule shows above the composer: in
  ``strict``, the banner and "Make a reflection" replace the text field.
  The reflection is the form of a direct conversation, its draft restored
  from the one the guide wrote; it goes through ``/linkup/v1/livechat/*``.
  The card of a reflection of the member offers its confirmation and its
  rejection, nothing else.
* "Need help now" stays under a welcome conversation, with the "?" of the
  guide mode. It shows the resources at once (``/linkup/v1/livechat/help``),
  saves the conversation if needed, then ``/linkup/v1/livechat/help_now``
  creates the urgent report and brings a moderator, or leaves the report
  in the queue; a status line says which.
* The widget reads the categories through
  ``/linkup/v1/livechat/categories``: a visitor reads no model.
* For a member logged in, the button of the widget opens Discuss.
* The guide mode reaches the elements of the widget inside its shadow
  root: their numbers, their sheet and their explanation.

Side of the operator
====================

In Discuss, the card of a reflection of a visitor shows as the card of a
member: its recipient confirms it or rejects it through the routes of the
live chat, and reports the visitor
(``action_report_livechat_visitor``), who cannot be blocked. The member
writes a reflection to the visitor from the composer of the conversation,
under the same start rule. A report of distress made in Discuss says
whether a person of the moderation joins, and opens the conversation.

Operation
=========

* Add the volunteer members as operators of "LinkUp welcome"; they need
  no live chat group. The distress channel takes its operators from the
  moderator group: leave its operators empty.
* The rating of an operator by a visitor is a measure of ego
  (LU-NF-032): ``/im_livechat/feedback`` records nothing on a LinkUp
  channel, and its rating page does not exist.
* The uninstallation deletes the reflections that have a visitor as a
  party, whose columns leave with the module.

Choices
=======

Decided by the owner:

* Q-43: the points of a visitor wait until their verified signup, then
  are paid once; the member operator earns theirs at the same moment.
* Q-44: a distress opens a conversation with a moderator online; without
  one, the help resources show at once and the report waits, urgent.
* Q-45: the widget is the one of ``website_livechat`` on the pages of the
  website; a logged-in member is sent to Discuss.

Applied by default, to confirm:

* Q-43: the values of the points are those of the scale of the members;
  an event waits 30 days at most (``linkup.guest_event_expiry_days``).
* Q-43: the rules apply at the verified signup as to any event: the new
  account is younger than ``linkup.points_min_account_hours`` (72), so
  its own lines are written without points (``new_account``), and the
  member operator earns theirs; a pair of a visitor and a member earns
  its confirmation once.
* The welcome rule shows the widget on every page (``regex_url`` empty).
* A visitor opens at most 20 welcome sessions an hour from one address
  (``linkup.livechat_sessions_per_ip_hour``).
* No live chat group for the member operators; the rating of an operator
  is off on the LinkUp channels.
* A distress conversation is read by its two parties only, an
  administrator of Odoo included: the moderators read the report in the
  console, not the conversation.
* "Need help now" pressed once a member operates the conversation creates
  the urgent report and shows the resources, without bringing a moderator
  into a conversation that holds a third person.
* The reading of a reflection of the live chat is not recorded: nothing
  depends on it, its withdrawal not being offered.

Not covered yet
===============

* The guide of a member opened from Discuss
  (``linkup.reflet.linkup_start_guide``): the chatbot runs in the widget
  only.
* The retention of the conversations of the visitors follows
  ``im_livechat``; their periods in LinkUp are to define (Q-31).

License
=======

AGPL-3.0 or later.
