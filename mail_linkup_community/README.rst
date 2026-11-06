=========================
LinkUp — Public community
=========================

Opens a LinkUp instance to a public community: anybody signs up, gives
their consents, confirms their address and keeps a profile under a
pseudonym; members report and block, moderators process the reports in a
console of their own, and the help in distress stays one click away.

Public signup
=============

* ``/web/signup`` of ``auth_signup``, opened (``auth_signup.invitation_scope
  = b2c``) at the installation, as is ``base.template_portal_user_id``,
  set to the member template of ``mail_linkup_reflet``: a new account is an
  internal user of the member group only, whose home action is the Reflet
  view, and sees Discuss only (LU-F-110 RM1, RM2). A template that would
  give more, an administration, the moderation, the contacts or the
  technical features, creates no account.
* The form adds, under the fields of ``auth_signup``, the consents, each
  one apart and none checked in advance (terms of use, privacy policy,
  processing of sensitive information; optional: links visible, energy
  visible, notifications), the attestation of being 18 or older with an
  age range, never a date of birth, and the declaration of living in
  Canada. The name is a pseudonym, unique or not (LU-F-113 RM1).
* ``res.users._signup_create_user`` checks everything again on the server
  (``_linkup_check_signup``): an empty trap field, a pseudonym, a valid
  address neither used nor banned nor of a domain of
  ``linkup.disposable_email_domains`` (subdomains included), the three
  required consents, the age and the residence. Any refusal leaves no
  account.
* While addresses are verified, the page tells nobody which addresses
  have an account (LU-NF-009): a free, used or banned address gets the
  same answer, "check your mailbox", and no session; the person logs in
  once the address is confirmed. A used address receives an email that
  tells how to log in, at most one per
  ``linkup.verification_resend_minutes``; a banned one receives nothing.
  Each try counts against the limit by address. ``signup_email``, which
  would send a known address to the login page with its login, is
  ignored, and the page of a forgotten password answers an unknown address
  as a known one.
* Beyond ``linkup.signup_rate_per_ip_hour`` (3) signups of one address IP
  in the hour, the page answers HTTP 429 and the model refuses with
  ``linkup.rate_limited``. The limits count keyed hashes of the address in
  ``linkup.rate.event``, purged after two days; no address is kept. An
  IPv6 address counts as its /64 network. The address is the one of the
  connection: ``X-Forwarded-For`` counts only with ``proxy_mode``, behind
  the proxy of the instance (LU-NF-007), without which every signup
  shares the address of the proxy.
* The login is a technical identifier (``lu-`` and 16 hexadecimal
  characters) that never holds the address (LU-F-113 RM2); the member logs
  in with their address, which ``_get_login_domain`` also matches for
  these logins. An address is used by one account only.
* The account starts unverified (``linkup_email_verified``) and receives a
  link ``/linkup/verify/<token>``, 256 random bits stored as a hash, valid
  24 hours and once. Until the click, every exchange is refused with
  ``linkup.not_verified``: sending a reflection, answering one, an
  invitation, a highlight; reading stays possible. A new link waits
  ``linkup.verification_resend_minutes`` (10), then ``linkup.rate_limited``.
  An account created by an administrator is verified. A member who changes
  their address, through the profile or the preferences of Odoo, gets the
  same checks and a new link.
* The signup through an invitation link takes the same form; the address
  of the invitation is verified by the signup itself (LU-F-020 RM4), any
  other address receives its link.

Consents
========

* ``linkup.consent`` keeps one row per decision: member, purpose, granted
  or withdrawn, version of the text (``linkup.consent_version.<purpose>``,
  "1" when unset), date, and a keyed hash of the address IP. The latest
  row of a purpose is its state.
* Members read their own rows and write none (LU-F-111 CA3); the server
  records them at the signup and through ``action_grant`` /
  ``action_revoke``, which force the current user. LinkUp administrators
  read them all (menu LinkUp › Consents).
* An account of the signup (``linkup_consent_required``), or every member
  when the setting "Consents of every member" is on, sends nothing without
  the terms, the privacy policy and the processing of sensitive
  information: ``linkup.consent_required`` (CA2). Withdrawing the latter
  stops the sendings at once. The terms and the privacy policy are not
  withdrawn: leaving them is deleting the account.
* The visibility of the links and of the energy are the preferences
  ``linkup_links_visible`` and ``linkup_energy_visible`` of
  ``mail_linkup_network``, which this module does not depend on: when they
  exist, every write of one, from the Network view or elsewhere, records
  the consent, and granting or withdrawing the consent writes the
  preference. Without that module, these purposes are not offered. The
  same holds for ``linkup_ai_consent`` of the AI module.
* The consent to notifications turns the notifications of LinkUp
  (``res.users.settings``) on or off together.

Profile
=======

* Client action ``linkup.profile`` (``/odoo/linkup-profile``, menu LinkUp ›
  My profile), opened by Email, Phone, Photo and Privacy of the menu of the
  avatar on their section: pseudonym, photo, language (fr_CA, en), address
  with its verification, optional phone, who may send a first reflection,
  the personal code, the consents with the date and version of the last
  decision, and the declarations of the signup.
* A last section, My data, downloads the data and deletes the account
  (see Personal data).
* ``res.users.linkup_profile_info`` and ``linkup_profile_write`` serve it;
  ``/linkup/v1/me/settings`` and ``/linkup/v1/me/verification`` delegate
  to them for the mobile client. A new address is verified again.
* ``linkup_first_reflet_scope`` (``nobody``, ``code``, ``email_or_code``,
  ``code`` by default) is in ``SELF_READABLE_FIELDS`` and
  ``SELF_WRITEABLE_FIELDS``; the suspension, the verification, the age and
  the residence are not (LU-F-082 CA2).
* What a restricted member reads of the others (LU-F-082 RM2, RM3, CA1,
  LU-F-112 RM3, CA3, LU-NF-009): the address, the phone and the login of
  any other user or partner are blanked in every reading, and never
  matched by their searches, those of Discuss included; the Discuss Store
  never carries the address of a member. The address of the author of a
  message (``email_from``, ``reply_to``) is blanked and never searched the
  same way, and a display name holds no address, whatever ``show_email``
  says. The photo of another member reaches only the members of an
  ``active`` link: the readings blank it, and ``/web/image`` serves the
  placeholder (``ir.binary``).

Discovery and NewLink
=====================

* No directory (LU-F-112): a member reaches another one through their
  scope, an invitation by address, a share link, or the personal code the
  other gave them (ten characters without the letters and digits read one
  for the other, shown in the profile, replaced by "New code").
* NewLink by phone (LU-F-020 RM3): LinkUp sends nothing; the answer of the
  sending, and of "Send the link again", holds the share link, which the
  Reflet view shows once with "Copy the link". The reflection is attached
  when the person who uses the link types the number of the invitation, at
  the signup or logged in; after five wrong numbers typed by a member, the
  invitation expires.
* NewLink by code: the invitation reaches the member of the code inside
  LinkUp (``linkup.invitation/received``). A code naming nobody gives the
  same answer and reaches nobody, so that the answers tell nothing of the
  codes; the daily limit of the invitations bounds the tries.
* The preference of the member decides what reaches them: ``nobody``,
  ``code`` (an invitation to their address then reaches nobody), or
  ``email_or_code``. An unverified account receives nothing. The inviter
  reads the same answer in every case.

Reports
=======

* A member reports a message from its menu ("Report", Discuss), a
  reflection from its card, and a member from the LinkUp panel of their
  conversation ("Report <name>"), with one of the nine reasons of
  LU-F-114 RM2 and an optional comment. ``action_create_report`` also
  takes ``partner_id``; ``/linkup/v1/report`` serves the mobile client and
  answers whether the report is urgent and the delay of an urgent one.
* A threat, a minor in danger or a person in distress is urgent: the
  report is due within ``linkup.report_urgent_hours`` (24), another one
  within ``linkup.report_due_hours`` (72). An urgent report reaches at
  once every moderator who may process it, on the bus
  (``linkup.moderation/urgent``, the id only) and by an email naming
  neither the content, the reason nor the reporter.
* The reporter reads their reports in their profile, as received, in
  review or processed, never the decision about the other member; the
  reported member never reads a report, nor who made it.
* The block of ``mail_linkup_reflet`` has its screen in the profile too
  (LU-F-115 RM3): the blocked members, each with "Unblock".
  ``/linkup/v1/block`` blocks and unblocks for the mobile client.

Moderation
==========

* Menu LinkUp › Moderation (``/odoo/linkup-moderation``), for the
  moderator group (LU-F-116): the counters of the queue (open, urgent,
  late, LU-NF-042), the queue, urgent first then by date, and a report on
  what deciding needs: reason, comment, reporter, state, due date,
  decision, the counters of the history of the member, the audit log.
* Conflicts of interest (RM5): ``linkup.report.linkup_moderator_conflict``,
  searched for the current user at each query, holds the reports a user
  made, those about them, those whose reporter or reported member shares
  a link with them in any state, and an appealed report for the moderator
  who decided it. The record rule of the moderators excludes them, and the
  console excludes them for everybody, administrators included. A
  moderator still reads, as a member, the reports they made, and
  processes none of them.
* The content is served apart, on demand ("Show the content"): the
  reported reflection or message and ``linkup.moderation_context_messages``
  (3) messages before and after it, nothing else of the conversation
  (RM1, RM4); the rejected reflections without their texts for an
  automatic report; nothing for a reported member. Moderators read no
  conversation they are not in, with or without a report (CA2).
* Decisions, on a report taken, each with a required reason: dismiss,
  hide the content, warn, suspend for 1 to 365 days
  (``linkup.suspension_days``, 7), ban. Hiding moves the body and the
  attachments of the message, and the texts of its reflection, to
  ``linkup.hidden.content``, which no access right opens: every member of
  the thread reads "Message hidden by the moderation", by Discuss, the
  ORM, a search or ``/web/content`` alike (CA1). A ban archives the
  account and keeps a hash of its address 24 months
  (``linkup.email.blocklist``, ``banned``, RM6); the signup and a change
  of address refuse it. A LinkUp administrator is neither warned,
  suspended nor banned by the console.
* The member a decision concerns reads it in their profile
  (``linkup.moderation.notice``): the decision, its reason, the end of a
  suspension, never the report. They contest it once within
  ``linkup.appeal_days`` (14) days; the report goes back to the queue,
  where another moderator upholds or reverses it, which puts the content
  back and lifts the suspension. A ban is contested by answering its
  email. The Reflet view shows a banner while a decision is unread.
* ``linkup.audit.log`` (LU-NF-040): who, when, what, why, for every
  reading of content, every decision and every change of a report a
  moderator makes through the ORM. Rows are only added: nobody writes or
  deletes one, even under ``sudo``, but a purge that says so. Moderators
  read the rows of the reports they may process (menu LinkUp ›
  Moderation audit log), administrators all, members none.

Help in distress
================

* "Need help now" heads the LinkUp help and has its entry in the user
  menu (LU-F-118 RM2, CA1): LinkUp is not an emergency service, and the
  resources of ``linkup.help_resources``, one per line, come first; empty,
  the crisis line 9-8-8 and the emergency number 9-1-1 of Canada show.
  ``linkup.moderation_hours`` tells when the moderation reads, the
  resources standing in outside these hours.
* Choosing the reason "person in distress" shows these resources at once,
  and again in the acknowledgement; the report is urgent (RM1, CA2).
  Nothing analyses the content (RM4).
* Procedure of the moderation for a report of distress (LU-NF-042): the
  report heads the queue and is due within the urgent delay; the
  moderator takes it, reads the content and its context, and closes it
  with a reason written to the audit log. The person in distress is
  pointed to the help resources, by a conversation when the moderator
  shares one with them. For an imminent danger, the reporter is the one
  to call the emergency services: LinkUp holds no location of a member.
  The moderation neither diagnoses nor replaces a help line, and the
  terms of use say that LinkUp is not an emergency service.

Personal data
=============

* Export (LU-F-117 RM1, LU-NF-014): "Download my data" in the profile, and
  ``/linkup/v1/me/export`` for the mobile client, give the session user a
  JSON file (``linkup.personal_data``, version 1): profile, every consent
  decision, the reflections written and received with their texts, the
  messages written as plain text with the names of their attachments, the
  points ledger and its balance, the links, the highlights, the
  invitations sent, the reports made, the blocked members and the
  decisions of the moderation. The route takes no identifier: nobody
  exports another account. The other party of an exchange is named by
  their pseudonym only; a reflection between two other members, a received
  reflection its recipient no longer reads (withdrawn, phantom) and the
  hidden themes of another author never appear.
* Deletion (RM2, RM3): "Delete my account" asks for a confirmation and
  sets ``linkup_deletion_requested_date``; the account is erased once
  ``linkup.deletion_grace_days`` (30) are over, and "Cancel the deletion"
  stops it meanwhile (LU-F-026 RM4). ``/linkup/v1/me/delete`` does the
  same, ``cancel`` cancelling. An administrator account is closed by
  another administrator.
* The erasure (``linkup.personal.data._linkup_erase_accounts``, Q-23):
  the pseudonym becomes "Deleted member"; the address, the phone, the
  photo, the age range, the residence, the personal code and the login
  leave; the password is replaced, which ends the sessions, and the
  account is archived. The texts of the reflections written and received
  are emptied (``linkup_content_removed``: every card says "Content
  removed"), the messages written lose their body, subject, attachments,
  voice messages and link previews, the reactions and stars go, and the
  carrier messages and the direct conversations are named again. The
  history of the partner (its tracking values hold the former address),
  its followers, notifications and emails, the login and device logs and
  the API keys are deleted; the invitations sent or received, the drafts
  and the unsent reflections too. The consents stay as proof, without the
  hash of their address.
* What the other party keeps: the reflection, its category, states and
  dates, without its texts, and the conversation, without the messages of
  the erased member. The points ledger stays whole, the erased account
  holding its lines: the karma of every member keeps equal to the sum of
  their lines (LU-NF-043), and the energy of the links of the others does
  not move.
* A content an open report points to (a reflection, a message, or the
  original the moderation hid) stays until the report is closed:
  ``linkup_erase_pending`` marks the account, and the retention cron
  erases it at its first run after the closing.
* The recipient of a rejected or inaccurate reflection erases its texts
  with "Erase its content" on its card (``action_erase_content``, RM4),
  unless an open report points to it.

Retention
=========

The cron "LinkUp: retention of the personal data" runs every day
(LU-NF-015, Q-31); each period is a setting (Settings › LinkUp › Personal
data), a value below 1 falling back to its default:

* deletions past ``linkup.deletion_grace_days`` (30): the account is
  erased;
* accounts of the public signup never verified within
  ``linkup.retention_unverified_days`` (30): erased; an account verified
  once (``linkup_verified_date``) whose new address waits for its link
  stays;
* drafts unchanged for ``linkup.retention_draft_days`` (30): deleted;
* reflections rejected or expired for
  ``linkup.retention_closed_reflet_months`` (12): texts erased, metadata
  kept;
* pairs without a reflection, a call or a message for
  ``linkup.retention_inactive_pair_months`` (24): the texts of their
  reflections and the content of their direct conversation are erased;
* reports closed for ``linkup.retention_closed_report_months`` (24):
  deleted with their audit log, their notices and the originals of the
  content they hid, which stays hidden;
* the invitations and the content of their ``pending_invite``
  reflections one day after their expiry (LU-NF-052), and the blocklist
  of addresses after 24 months: cron of ``mail_linkup_reflet``; the events
  of the limits after two days: cron of this module.

A run catches up whatever an earlier one left, so the purges replay by
themselves after the restoration of a backup.

Operation
=========

* No applicative encryption of the content (Q-38): the instance relies on
  the encryption of the disk of its database and filestore, and of its
  backups; the backups rotate within 90 days, so that an erased content
  leaves them too (LU-NF-015, LU-NF-019).
* Content and administration (LU-NF-053): a LinkUp administrator reads no
  reflection of two other members through the ORM; the moderators read a
  content only through a report, each reading written to the audit log.
* With the ``website`` module installed, the signup reads the setting of
  the current website (Website › Settings › Customer Account) in place of
  ``auth_signup.invitation_scope``: it stays "Free sign up" for LinkUp to
  be open. ``im_livechat_linkup_reflect``, which brings the website, sets
  it on the default website at its installation.
* Incidents of confidentiality (LU-NF-016): the register and the
  procedure of notice are kept outside the application, by the person in
  charge of the protection of personal information (LU-NF-010). The
  application gives them the audit log of the moderation and the export
  of an account.

Choices
=======

The entry questions of the lot apply the recommendation of the
specification, to confirm:

* Q-21: discovery by invitation or code only; no search by pseudonym.
* Q-22: 18 years and over; the age is an attestation with a range, never a
  date of birth; no minor accounts, so LU-F-119 does not apply.
* Q-23: deletion erases the content of the member, the reflections they
  received included, and keeps the ledger whole under the anonymized
  account; the other party keeps the metadata of their exchanges.
* Q-25: NewLink by phone is a share link; no SMS gateway. Typing the
  number stands for its verification, which an SMS would otherwise prove.
* Q-27: a pseudonym, the photo visible to the linked members only.
* Q-31: the retention periods proposed by the specification, each a
  setting (see Retention); 30 days for an account never verified, which
  the specification does not set. The rejected and expired reflections and
  the inactive pairs lose their texts rather than their records, which the
  ledger of the other party points to.
* Q-32: Canada only, by a declaration at signup, without geolocation; the
  terms of use state it.
* Q-38: no applicative encryption of the content; the disk and the
  backups are encrypted by the operation (see Operation).
* Captcha: none. The only native captcha of ``/web/signup`` sends the
  address IP to a third party; the limits, the disposable domains and the
  trap field stand instead.
* The accounts created by an administrator are verified and their consents
  are gathered outside the application, unless "Consents of every member"
  is on.
* A suspension keeps the login, against "disables the login" of LU-F-116
  RM2: the member then reads the decision and contests it in the
  application, and sends nothing, as LU-F-115 RM4 says. A ban archives
  the account.
* Moderators see the pseudonym of the reporter, as the mock-up shows it;
  the reported member never does.
* A report other than urgent is due within 72 hours, and a decision is
  contested within 14 days; both are settings.
* "Pieces" of a report are the reported content and its context, served
  on demand; a member attaches no file to a report.
* The erased account is archived, not deleted: the points ledger and the
  reflections of the other members point to it.
* A public signup does not log in while addresses are verified: the
  answer is the same for an address that has an account, which a session
  would betray. With ``linkup.email_verification`` off, the native signup
  logs in at once and tells that an address is used.
* A LinkUp administrator, like a moderator, neither reads nor processes
  nor deletes a report in a conflict of interest with them, nor its audit
  log; a moderator reads no block held on them.

Not covered yet
===============

* The logs of the AI assistance (30 days, LU-NF-015) belong to the module
  of the AI.
* The mobile application does not use the routes of the profile, the
  report, the block and the personal data yet.

License
=======

AGPL-3.0 or later.
