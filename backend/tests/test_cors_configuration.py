"""Offline regression tests for CORS configuration in AURA.

Tests environment variable parsing of CORS_ORIGINS across both JSON array and
comma-separated string formats, including whitespace, multi-origin, and FastAPI
middleware integration without live network dependencies.
"""

import os
from typing import List
import pytest
from starlette.testclient import TestClient

from app.config import Settings
from app.main import create_application


class TestCorsConfiguration:
    """Tests Pydantic Settings CORS_ORIGINS parsing and validation."""

    def test_cors_default_origins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies default origins when CORS_ORIGINS is not set in the environment."""
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        settings = Settings()
        assert settings.CORS_ORIGINS == [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    def test_cors_json_array_single_origin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies parsing of a single-element JSON array."""
        monkeypatch.setenv("CORS_ORIGINS", '["https://frontend.example.com"]')
        settings = Settings()
        assert settings.CORS_ORIGINS == ["https://frontend.example.com"]

    def test_cors_json_array_multiple_origins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies parsing of a multi-element JSON array."""
        monkeypatch.setenv(
            "CORS_ORIGINS",
            '["https://frontend1.example.com", "https://frontend2.example.com"]',
        )
        settings = Settings()
        assert settings.CORS_ORIGINS == [
            "https://frontend1.example.com",
            "https://frontend2.example.com",
        ]

    def test_cors_json_array_with_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies whitespace trimming within JSON array elements and surrounding payload."""
        monkeypatch.setenv(
            "CORS_ORIGINS",
            '  [  " https://f1.example.com " ,  " https://f2.example.com "  ]  ',
        )
        settings = Settings()
        assert settings.CORS_ORIGINS == [
            "https://f1.example.com",
            "https://f2.example.com",
        ]

    def test_cors_comma_separated_single_origin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies parsing of a single origin string without commas."""
        monkeypatch.setenv("CORS_ORIGINS", "https://frontend.example.com")
        settings = Settings()
        assert settings.CORS_ORIGINS == ["https://frontend.example.com"]

    def test_cors_comma_separated_multiple_origins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies parsing of a comma-separated string containing multiple origins."""
        monkeypatch.setenv(
            "CORS_ORIGINS",
            "https://frontend1.example.com,https://frontend2.example.com",
        )
        settings = Settings()
        assert settings.CORS_ORIGINS == [
            "https://frontend1.example.com",
            "https://frontend2.example.com",
        ]

    def test_cors_comma_separated_with_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies whitespace trimming around comma-separated origins."""
        monkeypatch.setenv(
            "CORS_ORIGINS",
            "  https://frontend1.example.com  ,   https://frontend2.example.com   ",
        )
        settings = Settings()
        assert settings.CORS_ORIGINS == [
            "https://frontend1.example.com",
            "https://frontend2.example.com",
        ]

    def test_cors_comma_separated_trailing_and_empty_segments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies empty segments and trailing commas are safely discarded."""
        monkeypatch.setenv(
            "CORS_ORIGINS",
            "https://frontend1.example.com, ,https://frontend2.example.com,",
        )
        settings = Settings()
        assert settings.CORS_ORIGINS == [
            "https://frontend1.example.com",
            "https://frontend2.example.com",
        ]

    def test_cors_empty_and_whitespace_only_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies empty or blank environment variable values yield an empty list."""
        monkeypatch.setenv("CORS_ORIGINS", "")
        settings_empty = Settings()
        assert settings_empty.CORS_ORIGINS == []

        monkeypatch.setenv("CORS_ORIGINS", "   ")
        settings_spaces = Settings()
        assert settings_spaces.CORS_ORIGINS == []

    def test_cors_middleware_integration_restricts_origins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verifies FastAPI CORSMiddleware allows configured origins and rejects unlisted ones."""
        monkeypatch.setenv(
            "CORS_ORIGINS",
            "https://trusted-frontend.run.app,https://staging-frontend.run.app",
        )
        from app import config
        from app import main as app_main
        custom_settings = Settings()
        monkeypatch.setattr(config, "settings", custom_settings)
        monkeypatch.setattr(app_main, "settings", custom_settings)

        app = create_application()
        client = TestClient(app)

        # 1. Allowed origin request
        res_allowed = client.get(
            "/health",
            headers={"Origin": "https://trusted-frontend.run.app"},
        )
        assert res_allowed.headers.get("access-control-allow-origin") == "https://trusted-frontend.run.app"

        # 2. Second allowed origin request
        res_allowed_2 = client.get(
            "/health",
            headers={"Origin": "https://staging-frontend.run.app"},
        )
        assert res_allowed_2.headers.get("access-control-allow-origin") == "https://staging-frontend.run.app"

        # 3. Disallowed origin request (not indiscriminate)
        res_disallowed = client.get(
            "/health",
            headers={"Origin": "https://evil.untrusted.com"},
        )
        assert "access-control-allow-origin" not in res_disallowed.headers
