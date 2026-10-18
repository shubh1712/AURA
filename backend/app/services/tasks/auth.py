"""AURA Cloud Tasks OIDC Authentication and Token Validation.

Validates Google-signed OpenID Connect (OIDC) identity tokens on internal worker endpoints,
verifying cryptographic signatures, token expiration, trusted issuer, audience, and the
authorized task-invoker service account identity.
"""

import logging
from typing import Any, Callable, Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import settings

logger = logging.getLogger(__name__)

# Trusted Google OIDC token issuers
VALID_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

# Test override for offline verification
_token_validator_override: Optional[Callable[[str, Optional[str]], Dict[str, Any]]] = None


def set_oidc_validator_override(
    override: Optional[Callable[[str, Optional[str]], Dict[str, Any]]]
) -> None:
    """Sets a global validator override for offline tests."""
    global _token_validator_override
    _token_validator_override = override


class OIDCValidator:
    """Validates Google-signed OIDC identity tokens for Cloud Tasks invocations."""

    def __init__(
        self,
        expected_audience: Optional[str] = None,
        expected_service_account: Optional[str] = None,
        cert_request: Optional[Any] = None,
    ) -> None:
        self.expected_audience = expected_audience or settings.AURA_OIDC_AUDIENCE or settings.AURA_CLOUD_TASKS_WORKER_URL
        self.expected_service_account = expected_service_account or settings.AURA_CLOUD_TASKS_SERVICE_ACCOUNT
        self._cert_request = cert_request or google_requests.Request()

    def verify(self, token: str) -> Dict[str, Any]:
        """Cryptographically verifies OIDC token and enforces identity constraints."""
        if _token_validator_override is not None:
            claims = _token_validator_override(token, self.expected_audience)
        else:
            try:
                claims = id_token.verify_oauth2_token(
                    token,
                    self._cert_request,
                    audience=self.expected_audience,
                )
            except Exception as exc:
                logger.warning("Cloud Tasks OIDC token cryptographic verification failed: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid or expired OIDC identity token: {exc}",
                ) from exc

        # 1. Enforce trusted Google issuer
        issuer = claims.get("iss")
        if issuer not in VALID_ISSUERS:
            logger.warning("Rejected OIDC token from untrusted issuer: %s", issuer)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OIDC identity token issuer is untrusted.",
            )

        # 2. Enforce email verification (if claim present)
        email_verified = claims.get("email_verified")
        if email_verified is not None:
            is_verified = (email_verified is True) or (str(email_verified).lower() == "true")
            if not is_verified:
                logger.warning("OIDC token email is unverified: %s", claims.get("email"))
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: caller email is not verified.",
                )

        # 3. Enforce authorized task invoker service account
        if self.expected_service_account:
            token_email = claims.get("email")
            if token_email != self.expected_service_account:
                logger.warning(
                    "OIDC identity mismatch: expected service account '%s', got '%s'",
                    self.expected_service_account,
                    token_email,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: caller '{token_email}' is not the authorized Cloud Tasks invoker.",
                )

        return claims


def get_oidc_validator() -> OIDCValidator:
    """Dependency provider for OIDCValidator."""
    return OIDCValidator()


async def verify_cloud_tasks_auth(
    request: Request,
    validator: OIDCValidator = Depends(get_oidc_validator),
) -> Dict[str, Any]:
    """FastAPI security dependency validating Google OIDC Bearer tokens on worker endpoints."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        # Never trust Cloud Tasks headers without cryptographic OIDC proof
        logger.warning("Cloud Tasks worker request rejected: missing Authorization header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Google OIDC identity token required.",
        )

    parts = auth_header.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed Authorization header. Format: 'Bearer <OIDC_TOKEN>'.",
        )

    token = parts[1].strip()
    return validator.verify(token)
