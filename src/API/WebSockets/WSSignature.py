import hmac
import hashlib


class SignatureManager:
    @staticmethod
    def create_signature(params: dict, secret_key: str) -> str:
        query_string = "&".join(
            [f"{key}={value}" for key, value in sorted(params.items())]
        )
        return hmac.new(
            secret_key.encode(), query_string.encode(), hashlib.sha256
        ).hexdigest()
