<p align="center">
  <img src="https://info.mollie.com/hubfs/github/odoo/logo.png" width="128" height="128"/>
</p>
<h1 align="center">Mollie addon for Odoo 10</h1>

## Installation
For installation instructions please refer to the odoo docs:
http://odoo-development.readthedocs.io/en/latest/odoo/usage/install-module.html#from-zip-archive-install

## Configuration
Go to Invoicing section -> Payments -> Payment Acquirers -> Mollie.  
Add API Keys (test and/or live) from your Mollie Account.

![alt text](/payment_mollie_official/static/description/crm_sc_02.png "Odoo mollie configuration example")

When Mollie acquirer is configured correctly, you can see Mollie payment option at the time of checkout.

Shopper will then be redirected to the Mollie payment method selection screen.

After a succesfull payment, a confirmation is shown to the shopper:

![alt text](/payment_mollie_official/static/description/crm_sc_02.png "Odoo mollie payment confirmation")

For Refunds: Activate module Cancel Journal Entries

![alt text](/payment_mollie_official/static/description/src/img/Cancel_Journal_Entry.JPG "Odoo mollie payment refunds")

For Specific Gateway Configuration: Go to gateways and change the Country, Amount or Currency that wil be used for specific gateways.

![alt text](/payment_mollie_official/static/description/src/img/Gateways.JPG "Odoo Mollie Gateways Configuration")

For Updating the available Payment Methods: Go to configuration and click update. The list is generated automatically based on the payment methods active in your Mollie account.

![alt text](/payment_mollie_official/static/description/src/img/Mollie_Configuration.JPG "Odoo Mollie Payment Methods")
