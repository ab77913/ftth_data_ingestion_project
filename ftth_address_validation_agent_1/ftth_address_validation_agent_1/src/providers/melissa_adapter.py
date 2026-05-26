import os
import requests
import urllib3
from src.models.schemas import CanonicalAddress, ProviderResult

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MelissaProvider:
    def __init__(self):
        self.license_key = os.getenv("MELISSA_LICENSE_KEY")

        self.url = "https://address.melissadata.net/v3/WEB/GlobalAddress/doGlobalAddress"

    def validate(self, address: CanonicalAddress) -> ProviderResult:

        if not self.license_key:
            return ProviderResult(
                provider="melissa",
                success=False,
                error="Missing Melissa credentials"
            )

        # params = {
        #     "id": self.license_key,
        #     "a1": f"{address.house_number} {address.street_name} {address.street_suffix}".strip(),
        #     "loc": f"{address.city} {address.state}",
        #     "postal": address.zip_code or "",
        #     "ctry": "US",
        #     "format": "json"
        # }

        params = {
            "id": self.license_key,
            "a1": f"{address.house_number} {address.street_name} {address.street_suffix}".strip(),
            "loc": address.city,
            "admarea": address.state,
            "postal": address.zip_code or "",
            "ctry": "US",
            "format": "JSON"
        }

        try:

            print("\n========== MELISSA REQUEST ==========")
            print(params)

            response = requests.get(
                self.url,
                params=params,
                timeout=30,
                verify=False
            )

            response.raise_for_status()

            data = response.json()

            print("\n========== MELISSA RAW RESPONSE ==========")
            print(data)

            records = data.get("Records", [])

            if not records:
                return ProviderResult(
                    provider="melissa",
                    success=False,
                    raw_response=data,
                    error="No records returned"
                )

            record = records[0]

            results = record.get("Results", "")

            return ProviderResult(
                provider="melissa",
                success=True,
                standardized_address=record.get("FormattedAddress"),
                dpv_match="Y" if "AV" in results else "N",
                zip_plus_4=record.get("PostalCode"),
                vacant=False,
                record_type=record.get("AddressType"),
                latitude=record.get("Latitude"),
                longitude=record.get("Longitude"),
                geocode_precision=record.get("AddressPrecisionCode"),
                unit_detected=bool(record.get("SubPremises")),
                raw_response=record,
            )

        except Exception as e:
            return ProviderResult(
                provider="melissa",
                success=False,
                error=str(e)
            )