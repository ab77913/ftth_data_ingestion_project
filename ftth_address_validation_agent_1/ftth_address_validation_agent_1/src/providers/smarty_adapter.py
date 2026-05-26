import os
import requests
import urllib3

from src.models.schemas import CanonicalAddress, ProviderResult

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SmartyProvider:

    def __init__(self):
        self.auth_id = os.getenv("SMARTY_AUTH_ID")
        self.auth_token = os.getenv("SMARTY_AUTH_TOKEN")

        self.url = "https://us-street.api.smarty.com/street-address"

    def validate(self, address: CanonicalAddress) -> ProviderResult:

        if not self.auth_id or not self.auth_token:
            return ProviderResult(
                provider="smarty",
                success=False,
                error="Missing Smarty credentials"
            )

        params = {
            "auth-id": self.auth_id,
            "auth-token": self.auth_token
        }

        payload = [{
            "street": f"{address.house_number} {address.street_name} {address.street_suffix}".strip(),
            "city": address.city,
            "state": address.state,
            "zipcode": address.zip_code or "",
            "candidates": 1
        }]

        try:

            print("\n========== SMARTY REQUEST ==========")
            print(payload)

            response = requests.post(
                self.url,
                params=params,
                json=payload,
                timeout=30,
                verify=False
            )

            response.raise_for_status()

            data = response.json()

            print("\n========== SMARTY RAW RESPONSE ==========")
            print(data)

            if not data:
                return ProviderResult(
                    provider="smarty",
                    success=False,
                    error="No records returned",
                    raw_response={}
                )

            item = data[0]

            analysis = item.get("analysis", {})
            components = item.get("components", {})
            metadata = item.get("metadata", {})

            zip_code = components.get("zipcode", "")
            plus4 = components.get("plus4_code", "")

            zip_plus_4 = (
                f"{zip_code}-{plus4}"
                if plus4 else zip_code
            )

            standardized_address = item.get("delivery_line_1", "")

            if item.get("last_line"):
                standardized_address += f" {item.get('last_line')}"

            return ProviderResult(
                provider="smarty",
                success=True,
                standardized_address=standardized_address,
                dpv_match=analysis.get("dpv_match_code"),
                zip_plus_4=zip_plus_4,
                vacant=analysis.get("vacant") == "Y",
                record_type=metadata.get("record_type"),
                latitude=metadata.get("latitude"),
                longitude=metadata.get("longitude"),
                geocode_precision=metadata.get("precision"),
                unit_detected=bool(components.get("secondary_number")),
                raw_response=item
            )

        except Exception as e:

            return ProviderResult(
                provider="smarty",
                success=False,
                error=str(e)
            )