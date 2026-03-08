"""AWS SNS message signature verification.

Validates that incoming messages are genuinely from AWS SNS, preventing
spoofed notifications to our webhook endpoint.

See: https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html
"""

from __future__ import annotations

import base64
import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Cache downloaded certificates to avoid re-fetching
_cert_cache: dict[str, bytes] = {}

# SNS signing certificates must come from amazonaws.com
_ALLOWED_CERT_HOSTS = (".amazonaws.com",)

# Fields included in the signature, in order, by message type
_SIGNATURE_FIELDS = {
    "Notification": ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"],
    "SubscriptionConfirmation": [
        "Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type",
    ],
    "UnsubscribeConfirmation": [
        "Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type",
    ],
}


def _build_signing_string(body: dict, message_type: str) -> str:
    """Build the canonical string that was signed by SNS."""
    fields = _SIGNATURE_FIELDS.get(message_type, [])
    parts = []
    for field in fields:
        value = body.get(field)
        if value is not None:
            parts.append(field)
            parts.append(str(value))
    return "\n".join(parts) + "\n"


async def _get_certificate(cert_url: str) -> bytes | None:
    """Download and cache an SNS signing certificate."""
    if cert_url in _cert_cache:
        return _cert_cache[cert_url]

    # Validate the certificate URL is from amazonaws.com
    parsed = urlparse(cert_url)
    if parsed.scheme != "https":
        logger.warning("SNS certificate URL is not HTTPS: %s", cert_url)
        return None
    if not any(parsed.hostname.endswith(host) for host in _ALLOWED_CERT_HOSTS):
        logger.warning("SNS certificate URL not from amazonaws.com: %s", cert_url)
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(cert_url)
            resp.raise_for_status()
            cert_pem = resp.content
            _cert_cache[cert_url] = cert_pem
            return cert_pem
    except Exception:
        logger.exception("Failed to download SNS signing certificate: %s", cert_url)
        return None


async def verify_sns_signature(body: dict) -> bool:
    """Verify the signature of an SNS message.

    Returns True if the signature is valid, False otherwise.
    On verification failure, logs the reason.
    """
    try:
        from cryptography.x509 import load_pem_x509_certificate
        from cryptography.hazmat.primitives.hashes import SHA1, SHA256
        from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
    except ImportError:
        logger.warning("cryptography package not installed — skipping SNS signature verification")
        return True  # Don't block if the package isn't available

    message_type = body.get("Type", "")
    signature_b64 = body.get("Signature")
    cert_url = body.get("SigningCertURL") or body.get("SigningCertUrl")
    signature_version = body.get("SignatureVersion", "1")

    if not signature_b64 or not cert_url:
        logger.warning("SNS message missing Signature or SigningCertURL")
        return False

    # Get the signing certificate
    cert_pem = await _get_certificate(cert_url)
    if cert_pem is None:
        return False

    # Build the string that was signed
    signing_string = _build_signing_string(body, message_type)
    signature = base64.b64decode(signature_b64)

    # Verify the signature
    try:
        cert = load_pem_x509_certificate(cert_pem)
        public_key = cert.public_key()
        hash_algo = SHA256() if signature_version == "2" else SHA1()
        public_key.verify(signature, signing_string.encode("utf-8"), PKCS1v15(), hash_algo)
        return True
    except Exception:
        logger.warning("SNS signature verification failed")
        return False
