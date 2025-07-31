odoo.define("survey_matrix_selection.survey_submit", function (require) {
    "use strict";
    var SurveyFormWidget = require("survey.form");
    /*
     * Including custom events to SurveyFormWidget
     */
    SurveyFormWidget.include({
        events: {
            "change .o_file": "_onChangeFile",
            "change .o_survey_form_choice_item": "_onChangeChoiceItem",
            "click .o_survey_matrix_btn": "_onMatrixBtnClick",
            'click input[type="radio"]': "_onRadioChoiceClick",
            'click button[type="submit"]': "_onSubmit",
            "click .o_survey_choice_img img": "_onChoiceImgClick",
            "focusin .form-control": "_updateEnterButtonText",
            "focusout .form-control": "_updateEnterButtonText",
        },
        _prepareSubmitValues: function (formData, params) {
            // this is a copy from survey_matrix_selection method _prepareSubmitValues
            var self = this;
            formData.forEach(function (value, key) {
                switch (key) {
                    case "csrf_token":
                    case "token":
                    case "page_id":
                    case "question_id":
                        params[key] = value;
                        break;
                }
            });
            // Get all question answers by question type
            var address = {};
            var names = {};
            var matrix = {};
            var self = this;
            this.$("[data-question-type]").each(function () {
                switch ($(this).data("questionType")) {
                    case "text_box":
                    case "char_box":
                    case "numerical_box":
                        params[this.name] = this.value;
                        break;
                    case "date":
                        params = self._prepareSubmitDates(params, this.name, this.value, false);
                        break;
                    case "datetime":
                        params = self._prepareSubmitDates(params, this.name, this.value, true);
                        break;
                    case "simple_choice_radio":
                    case "multiple_choice":
                        params = self._prepareSubmitChoices(params, $(this), $(this).data("name"));
                        break;
                    case "url":
                        params[this.name] = this.value;
                        break;
                    case "email":
                        params[this.name] = this.value;
                        break;
                    case "many2one":
                        params[this.name] = [this.value, $(this).find("option:selected").attr("data-value")];
                        break;
                    case "week":
                        params[this.name] = this.value;
                        break;
                    case "color":
                        params[this.name] = this.value;
                        break;
                    case "time":
                        params[this.name] = this.value;
                        break;
                    case "range":
                        params[this.name] = this.value;
                        break;
                    case "password":
                        params[this.name] = this.value;
                        break;
                    case "month":
                        params[this.name] = this.value;
                        break;
                    case "address":
                        address[this.name] = this.value;
                        if (this.name.endsWith("pin")) {
                            (address[this.name.split("-")[0] + "-country"] = self.$el
                                .find(`#${this.name.split("-")[0] + "-country"}`)
                                .val()),
                                (address[this.name.split("-")[0] + "-state"] = self.$el
                                    .find(`#${this.name.split("-")[0] + "-state"}`)
                                    .val());
                            params[this.name.split("-")[0]] = address;
                            address = {};
                            break;
                        }
                        break;
                    case "custom":
                        if (this.name == "matrix-end") {
                            params[this.id] = matrix;
                        }
                        if ($(this).attr("id") === "select" && this.name) {
                            matrix[this.name] = $(this).find("option:selected").attr("data-value");
                        }
                        if ($(this).attr("id") !== "select" && this.name) {
                            matrix[this.name] = this.value;
                        }
                    case "matrix":
                        // Only the matrix case is different from origin code
                        let questionId = $(this).data("name");
                        // Try to detect data-force-type-selection information
                        let table = $(this).parent().find("table.data-force-type-selection");
                        if (table.length === 0) {
                            params = self._prepareSubmitAnswersMatrix(params, $(this));
                        } else {
                            let value_select = {};
                            let selects = table.find("select").each(function () {
                                let row_id = $(this).data("row-id");
                                value_select[row_id] = [$(this).find(":selected").data("answer-id")];
                            });
                            params[questionId] = value_select;
                            params = self._prepareSubmitComment(
                                params,
                                $(this).closest(".js_question-wrapper"),
                                $(this).data("name"),
                                true
                            );
                        }
                        break;
                    case "name":
                        names[this.name] = this.value;
                        if (this.name.endsWith("last")) {
                            params[this.name.split("-")[0]] = names;
                            break;
                        }
                        break;
                    case "selection":
                        params[this.name] = this.value;
                        break;
                    case "file":
                        if ($(this)[0].files[0]) {
                            params[this.name] = [$(this).data("file-name"), $(this)[0].files[0]["name"]];
                            break;
                        }
                        break;
                    case "many2many":
                        params[this.name] = self.$el.find(`.${this.name}`).val();
                        break;
                }
            });
        },
    });
});
