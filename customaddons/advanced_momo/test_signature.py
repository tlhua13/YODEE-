import hmac
import hashlib
from collections import OrderedDict


def generate_momo_signature(data: dict, access_key: str, secret_key: str) -> str:
    """
    Generate MoMo Hmac_SHA256 signature
    """
    # Fields MoMo yêu cầu (đã sort a–z)
    raw_data = OrderedDict({
        "accessKey": access_key,
        "amount": str(data["amount"]),
        "extraData": data.get("extraData", ""),
        "ipnUrl": data["ipnUrl"],
        "orderId": data["orderId"],
        "orderInfo": data["orderInfo"],
        "partnerCode": data["partnerCode"],
        "redirectUrl": data["redirectUrl"],
        "requestId": data["requestId"],
        "requestType": data["requestType"],
    })

    raw_signature = "&".join(f"{k}={v}" for k, v in raw_data.items())

    signature = hmac.new(
        secret_key.encode("utf-8"),
        raw_signature.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return signature, raw_signature

payload = {
    "ipnUrl": "https://yodee.hungnamecommerce.com/api/momo/call_back_data",
    "redirectUrl": "https://yodee.hungnamecommerce.com",
    "requestId": "b886046e-389b-4a9d-8e0e-7444cb1b7d8d",
    "orderId": "Order 00016-008-0001_b886046e",
    "amount": "129600",
    "orderInfo": "Thanh toan Order 00016-008-0001",
    "requestType": "captureWallet",
    "partnerCode": "MOMOVTLS20230418",
    "extraData": ""
}

####### ENV PRODUCTION
access_key = "XbPkHyMOojr1DtJo"
secret_key = "UtCOnvmu4VNmVriHMi0jmRiZwOPeEUjh"

signature, raw = generate_momo_signature(payload, access_key, secret_key)

print("=== ENV PRODUCTION ===")
print("RAW:", raw)
print("SIGNATURE:", signature)


####### ENV TEST
access_key = "m8ZeLWp3JFGcgVXB"
secret_key = "QPbMOiIctpYm5Ige9iRzhgId47aeRxKP"
payload["partnerCode"] = "MOMOVTLS20230418_TEST"

signature, raw = generate_momo_signature(payload, access_key, secret_key)

print("=== ENV TEST ===")
print("RAW:", raw)
print("SIGNATURE:", signature)
