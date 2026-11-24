import json
import logging

import requests
from werkzeug import urls

from odoo import models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class MolliePosTerminal(models.Model):
    _inherit = "mollie.pos.terminal"

    def _mollie_api_call(
        self, endpoint, data=None, params=None, method="POST", silent=False
    ):
        api_key = self.env.context.get("mollie_api_key")

        if not api_key:
            raise ValidationError(
                self.env._(
                    "Something went wrong: Mollie API key was not found in context."
                )
            )
        headers = {
            "content-type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        endpoint = f"/v2/{endpoint.strip('/')}"
        url = urls.url_join("https://api.mollie.com/", endpoint)
        querystring_params = self._mollie_generate_querystring(params)

        _logger.info("Mollie POS Terminal CALL on: %s", url)

        try:
            response = requests.request(
                method,
                url,
                params=querystring_params,
                json=data,
                headers=headers,
                timeout=60,
            )
            if response.status_code == 204:
                result = True  # returned no content
            else:
                result = response.json()
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            error_details = response.json()
            _logger.exception("MOLLIE-POS-ERROR \n %s", error_details)
            if silent:
                result = error_details
            else:
                raise ValidationError(
                    self.env._("MOLLIE: \n %s", error_details)
                ) from None
        except requests.exceptions.RequestException as e:
            _logger.exception("unable to communicate with Mollie: %s \n %s", url, e)
            if silent:
                result = {"error": "Some thing went wrong"}
            else:
                raise ValidationError(
                    self.env._("Mollie: Some thing went wrong.")
                ) from e
        finally:
            if self.mollie_debug_logging:
                message = str(json.dumps({"DATA": data, "RESPONSE": result}, indent=4))
                self._log_logging(self.env, message, method, url, self.id)
        return result
