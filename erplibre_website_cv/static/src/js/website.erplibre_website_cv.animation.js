odoo.define("erplibre_website_cv.animation", require => {
    "use strict";

    let sAnimation = require("website.content.snippets.animation");
    let ajax = require("web.ajax");

    sAnimation.registry.erplibre_website_cv = sAnimation.Class.extend({
        selector: ".o_erplibre_website_cv",

        start: function () {
            let self = this;

            this._informationsList = this.el.getElementsByClassName("informations-list")[0];
            this._form = this.el.getElementsByClassName("informations-form")[0];
            this._input = this.el.getElementsByClassName("informations__input")[0];
            this._originalContent = this._informationsList.innerHTML;

            this._input.value = "";

            const def = this.getInformations(self);

            this.updateInformations(self);
            this.addInformations(self);

            return $.when(this._super.apply(this, arguments), def);
        },

        getInformations: function (self) {
            let def = self._rpc({
                route: "/erplibre_website_cv/website_cv"
            }).then(function (data) {
                if (data.error) {
                    return;
                }

                if (_.isEmpty(data)) {
                    self._$loadedContent = data;
                    self._informationsList.innerHTML = "";
                    self._informationsList.parentElement.style.display = "none";
                    return;
                }

                self._$loadedContent = data;
                self._informationsList.innerHTML = "";
                self._informationsList.parentElement.removeAttribute("style");

                for (const information of data) {
                    const informationListItem = document.createElement("li");
                    informationListItem.className = "aliment";
                    informationListItem.id = aliment.id;

                    const informationText = document.createElement("span");
                    informationText.className = "information__text";
                    informationText.setAttribute("contenteditable", "true");
                    informationText.textContent = information.name;

                    const informationDelete = document.createElement("div");
                    informationDelete.className = "information__delete";

                    informationListItem.append(informationText);
                    informationListItem.append(informationDelete);
                    self._informationsList.append(informationListItem);
                }
            });

            return def;
        },
        addInformations: function (self) {
            self._form.addEventListener("submit", event => {
                event.preventDefault();

                ajax.jsonRpc(
                    "/erplibre_website_cv/website_add",
                    "call",
                    { "informations_name": self._input.value }
                ).done(data => {
                    if (data.error) {
                        return;
                    }

                    if (_.isEmpty(data)) {
                        return;
                    }

                    self._input.value = "";
                    self.getInformations(self)
                })
            });
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
                    "/erplibre_website_cv/website_update",
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
                this._informationsList.innerHTML = this._originalContent;
            }
        }
    });
});