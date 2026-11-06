==================
LinkUp — Live chat
==================

Extends ``im_livechat`` with the LinkUp rules.

* The website widget welcomes visitors without an account.
* A chatbot script guides a first reflection step by step.
* A distress report opens a conversation with an available moderator.
* A member operator and a visitor exchange reflections in the widget.

Status
======

Skeleton: the module installs and declares its dependencies:
``mail_linkup_reflet``,
``im_livechat``,
``mail_linkup_community``,
``website_livechat``.
Its features are not implemented yet, but one: the default website opens
the public signup of LinkUp at the installation (``auth_signup_uninvited =
b2c``), since the signup reads the setting of the website once
``website`` is installed, and that setting is "On invitation" by default.

License
=======

AGPL-3.0 or later.
