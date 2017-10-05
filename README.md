# Mollie addon for Odoo 10© 
This is the official Mollie addon for Odoo 10© 

## Installation
For installation instructions please refer to the odoo docs:
http://odoo-development.readthedocs.io/en/latest/odoo/usage/install-module.html#from-zip-archive-install

## Configuration
Go to Invoicing section -> Payments -> Payment Acquirers -> Mollie.  
Add API Keys (test and/or live) from your Mollie Account.

![alt text](/mollie-payments-plugin/images/odoo_configuration.png "Odoo mollie configuration example")

When Mollie acquirer is configured correctly, you can see Mollie payment option at the time of checkout.

Shopper will then be redirected to the Mollie payment method selection screen.

After a succesfull payment, a confirmation is shown to the shopper:

![alt text](/mollie-payments-plugin/images/payment_confirmation.png "Odoo mollie payment confirmation")
