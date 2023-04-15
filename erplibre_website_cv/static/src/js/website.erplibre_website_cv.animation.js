let john = null

odoo.define("erplibre_website_cv.animation", require => {
    "use strict";

    let sAnimation = require("website.content.snippets.animation");
    let ajax = require("web.ajax");

    sAnimation.registry.erplibre_website_cv = sAnimation.Class.extend({
        selector: ".o_erplibre_website_cv",

        start: function () {
            let self = this;

            john = this.el
            this.resumeSectionContent = this.el.getElementsByClassName("resume-section-content-propos")[0];
            console.log(this.resumeSectionContent);
            this._originalContent = this.resumeSectionContent.innerHTML;

            const def = this.getWebsiteCV(self);

            this._desctextList = this.el.getElementsByClassName("desc-text");
            for (const element of this._desctextList) {
                element.setAttribute("contenteditable", "true");
            }

            return $.when(this._super.apply(this, arguments), def);
        },
        getWebsiteCV: function (self) {
            let def = self._rpc({
                route: "/erplibre_website_cv/website_cv"
            }).then(function (data) {
                if (data.error) {
                    return;
                }

                if (_.isEmpty(data)) {
                    self._$loadedContent = data;
                    return;
                }

                self._$loadedContent = data;

                for (const contact of data) {
                    console.log(contact)
                    const emailElement = self.el.getElementsByClassName("email_p")[0];
                    if (emailElement) {
                        emailElement.setAttribute("href", "mailto:" + contact.email);
                        emailElement.textContent = contact.email;
                    }
                    self.el.getElementsByClassName("name_p")[0].textContent = contact.name
                    self.el.getElementsByClassName("phone_p")[0].textContent = contact.phone
                    self.el.getElementsByClassName("address_p")[0].textContent = contact.address
                    self.el.getElementsByClassName("description_p")[0].textContent = contact.description
                }
            });

            return def;
        },

        updateInformations: function (self) {
            self.el.addEventListener("keyup", event => {
                event.preventDefault();

                if (event.which === 13) {
                    event.target.innerHTML = event.target.textContent;
                    event.target.blur();
                    return false;
                }

                if (!event.target.classList.contains("informations__text")) {
                    return;
                }

                const informationsId = event.target.parentElement.id;
                const informationsName = event.target.textContent;

                ajax.jsonRpc(
                    "/erplibre_website_cv/website_cv",
                    "call",
                    {
                        "informations_id": alimentId,
                        "informations_name": alimentName
                    }
                ).done(data => {
                    return true;
                })
            });
        },
        destroy: function () {
            this._super.apply(this, arguments);
            if (this._$loadedContent) {
                this.resumeSectionContent.innerHTML = this._originalContent;
            }
        }
    });
});