from odoo import http, models, fields, api, exceptions

import json
import werkzeug

class WebsiteCVController(http.Controller):
    @http.route(
        ["/erplibre_website_cv/website_cv"],
        type="json",
        auth="public",
        website=True,
        methods=["POST", "GET"],
        csrf=False,
    )
    def website_cv_form(self, **post):
        Contact = http.request.env['website.cv']
        if http.request.httprequest.method == 'POST':
            # Get form data from POST request
            name = post.get('name')
            address = post.get('address')
            phone = post.get('phone')
            email = post.get('email')
            description = post.get('description')

            # Create a new contact record
            contact = Contact.create({
                'name': name,
                'address': address,
                'phone': phone,
                'email': email,
                'description': description,
            })

            # Redirect to a success page or return a JSON response
            # with the contact record data if needed
            return json.dumps({'result': 'success', 'contact_id': contact.id})
