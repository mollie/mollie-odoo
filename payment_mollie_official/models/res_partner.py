# -*- coding: utf-8 -*-

import phonenumbers
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _prepare_mollie_address(self):
        self.ensure_one()
        result = {}

        # Name
        name_parts = self.name.split(" ")
        result['givenName'] = name_parts[0]
        result['familyName'] = ' '.join(name_parts[1:]) if len(name_parts) > 1 else result['givenName']

        # Phone
        phone = self._mollie_phone_format(self.phone)
        if not phone:
            phone = self._mollie_phone_format(self.mobile)
        if phone:
            result['phone'] = phone
        result['email'] = self.email

        # Address
        street = []
        if self.street:
            street.append(self.street)
        if self.street2:
            street.append(self.street2)

        result["streetAndNumber"] = ' '.join(street) or ' '
        result["postalCode"] = self.zip or ' '
        result["city"] = self.city or ' '
        result["country"] = self.country_id and self.country_id.code or "BE"

        return result

    @api.model
    def _mollie_phone_format(self, phone):
        """ Only E164 phone number is allowed in mollie """
        phone = False
        if phone:
            try:
                parse_phone = phonenumbers.parse(self.phone, None)
                if parse_phone:
                    phone = phonenumbers.format_number(
                        parse_phone, phonenumbers.PhoneNumberFormat.E164
                    )
            except Exception:
                _logger.warning("Can not format customer phone number for mollie")
        return phone
