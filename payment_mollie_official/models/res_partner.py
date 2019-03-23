# -*- coding: utf-8 -*-
# #############################################################################
#
#    Copyright Mollie (C) 2019
#    Contributor: Eezee-It <info@eezee-it.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################

from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"
    _description = 'Res Partner'

    @api.multi
    def _get_mollie_address(self):
        self.ensure_one()
        name_split = self.name.split(' ')
        givenName = name_split[0]
        familyName = self.name.replace(name_split[0], '')
        res = {
            'givenName': givenName,
            'familyName': familyName or givenName,
            'streetAndNumber': "%s %s" % ((self.street or ''), (
                self.street2 or '')),
            'city': self.city or '',
            'postalCode': self.zip or '0000',
            'country': (self.country_id and
                        self.country_id.code) or 'nl',
            'email': self.email,
        }
        return res

