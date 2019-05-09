<p align="center">
  <img src="https://info.mollie.com/hubfs/github/odoo/logo.png" width="128" height="128"/>
</p>
<h1 align="center">Mollie addon for Odoo 12</h1>

## Quick guide
1. Download the Odoo module and add it under your custom apps in your Odoo configuration file (found under /etc/).
2. Install all Python packages with `pip3 install -r requirements.txt`
3. Restart your Odoo service so that Odoo can find and use all required Python packages.
4. Update your apps list from the 'Apps' menu in Odoo.
5. Install the Mollie app from the 'Apps' menu in Odoo.

## Installing the Python packages
You will need two Python packages for using this application.
You can install both these requirements by running the following command:
```
pip3 install -R requirements.txt
```
Alternatively you can install them manually by doing `pip3 install mollie-api-python==2.1.0` and `pip3 install phonenumbers==8.10.3`
You can find all the information about the dependencies on the following URL's:
https://pypi.org/project/mollie-api-python/2.1.0/ <br/>
https://pypi.org/project/phonenumbers/8.10.3/

After installing the Python packages you should **restart** your Odoo service to make sure that your Odoo instance can access and use the dependencies. If you get a 'mollie' keyerror it means Odoo cannot use your Python packages or that you've installed an old version from mollie-api-python.

## Installation
For installation instructions please refer to the odoo docs:
http://odoo-development.readthedocs.io/en/latest/odoo/usage/install-module.html#from-zip-archive-install

## Configuration
Go to Invoicing > Payments > Payment Acquirers -> Mollie.
Add the API Keys (test and/or live) from your Mollie Account here.

![alt text](/payment_mollie_official/static/description/crm_sc_02.PNG "Odoo mollie configuration example")

When the Mollie payment acquirer is configured correctly, you can see the Mollie payment option at the time of checkout. You will not see Mollie as long as there are no payment methods configured on the payment acquirer. You will first have to add payment methods to your account on the Mollie website and then click on the "Update payment methods" button under the tab "Configuration" of the payment method Mollie in Odoo.

The customer will then be redirected to the Mollie payment method selection screen.

After a succesfull payment, a confirmation is shown to the shopper:

![alt text](/payment_mollie_official/static/description/Payment_Confirmation.png "Odoo mollie payment confirmation")

If you'd like to use refunds you should activate the module "Cancel Journal Entries"

![alt text](/payment_mollie_official/static/description/Refund.png "Odoo mollie payment refunds")

![alt text](/payment_mollie_official/static/description/cancel_journal_entry.png "Odoo Cancel Journal Entry Module")

If you want to use a specific gateway configuration you should configure it under the "Mollie" payment method by clicking on the smart button "Gateways" at the top of the form. You can change the country, amount or currency that will be used for specific gateways here.

![alt text](/payment_mollie_official/static/description/gateways.png "Odoo Mollie Gateways Configuration")

For updating the available payment Methodp: Go to configuration and click on the button "Update payment methods". The list is generated automatically based on the payment methods that are configured in your Mollie account.

![alt text](/payment_mollie_official/static/description/mollie_configuration.png "Odoo Mollie Payment Methods")

