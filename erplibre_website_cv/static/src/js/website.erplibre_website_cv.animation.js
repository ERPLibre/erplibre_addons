odoo.define("erplibre_website_cv.animation", require => {
    "use strict";

    let sAnimation = require("website.content.snippets.animation");
    let ajax = require("web.ajax");

    sAnimation.registry.erplibre_website_cv = sAnimation.Class.extend({
        selector: ".o_erplibre_website_cv",

        start: function () {
            let self = this;

            this.resumeSectionContent = this.el.querySelector(".resume-section-content-apropos, .resume-section-content-experience, .resume-section-content-projets, .resume-section-content-formations, .resume-section-content-interets, .resume-section-content-trophes");
            this._originalContent = this.resumeSectionContent.innerHTML;

            const def = this.getWebsiteCV(self);

            this._desctextList = this.el.getElementsByClassName("desc-text");
            for (const element of this._desctextList) {
                element.setAttribute("contenteditable", "true");
                element.addEventListener("input", function (event) {
                    const contactId = self.el.dataset.contactId;
                    if (!contactId) {
                        throw new Error("Contact ID not provided.");
                    }
                    console.log(event.target.dataset);
                    const fieldName = event.target.dataset.fieldName;
                    const fieldValue = event.target.textContent.trim();

                    self.updateCV(contactId, fieldName, fieldValue);
                });

                element.addEventListener("click", function (event) {
                    console.log(getComputedStyle(event.target).borderColor);
                    event.target.style.backgroundColor = "#d3d3d3";
                    event.target.style.borderColor = "#d3d3d3 !important";
                });
                element.addEventListener("blur", function (event) {
                    event.target.style.backgroundColor = "";
                    event.target.style.borderColor = "";
                });
            }

            // Enable scrollspy on the body
            $('body').scrollspy({ target: '#navbarResponsive', offset: 100 });

            // Smooth scrolling on click of nav links
            $('a.js-scroll-trigger[href*="#"]:not([href="#"])').click(function () {
                if (location.pathname.replace(/^\//, '') == this.pathname.replace(/^\//, '') && location.hostname == this.hostname) {
                    var target = $(this.hash);
                    target = target.length ? target : $('[name=' + this.hash.slice(1) + ']');
                    if (target.length) {
                        $('html, body').animate({
                            scrollTop: target.offset().top - 70
                        }, 1000, 'easeInOutExpo');
                        return false;
                    }
                }
            });

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

                self.el.dataset.contactId = data[0].id;

                self._$loadedContent = data;

                for (const contact of data) {
                    console.log(contact)
                    const emailElement = self.el.getElementsByClassName("email_apropos")[0];
                    if (emailElement) {
                        emailElement.setAttribute("href", "mailto:" + contact.email);
                        emailElement.textContent = contact.email;
                    }
                    self.el.getElementsByClassName("name_apropos")[0].textContent = contact.name
                    self.el.getElementsByClassName("phone_apropos")[0].textContent = contact.phone
                    self.el.getElementsByClassName("address_apropos")[0].textContent = contact.address
                    self.el.getElementsByClassName("description_apropos")[0].textContent = contact.description

                    self.el.getElementsByClassName("name_experience")[0].textContent = contact.name_experience
                    self.el.getElementsByClassName("entreprise_name_experience")[0].textContent = contact.entreprise_name_experience
                    self.el.getElementsByClassName("description_experience")[0].textContent = contact.description_experience
                    self.el.getElementsByClassName("date_experience")[0].textContent = contact.date_experience

                    self.el.getElementsByClassName("name_projets")[0].textContent = contact.name_projets
                    self.el.getElementsByClassName("entreprise_name_projets")[0].textContent = contact.entreprise_name_projets
                    self.el.getElementsByClassName("description_projets")[0].textContent = contact.description_projets
                    self.el.getElementsByClassName("date_projets")[0].textContent = contact.date_projets

                    self.el.getElementsByClassName("name_formations")[0].textContent = contact.name_formations
                    self.el.getElementsByClassName("entreprise_name_formations")[0].textContent = contact.entreprise_name_formations
                    self.el.getElementsByClassName("description_formations")[0].textContent = contact.description_formations
                    self.el.getElementsByClassName("date_formations")[0].textContent = contact.date_formations

                    self.el.getElementsByClassName("name_interets")[0].textContent = contact.name_interets
                    self.el.getElementsByClassName("description_interets")[0].textContent = contact.description_interets

                    self.el.getElementsByClassName("name_trophes")[0].textContent = contact.name_trophes
                    self.el.getElementsByClassName("date_trophes")[0].textContent = contact.date_trophes
                }
            });

            return def;
        },
        updateCV: function (contactId, fieldName, fieldValue) {
            const params = {
                id: contactId,
                [fieldName]: fieldValue,
                toUpdateList: { fieldName: fieldName, fieldValue: fieldValue }
            }
            console.log(params)
            ajax.jsonRpc("/erplibre_website_cv/update_cv", "call", params).then(function (data) {
                if (data.success) {
                    console.log("Contact updated successfully.");
                } else {
                    console.error("Failed to update contact.");
                }
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