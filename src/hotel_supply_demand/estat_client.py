"""Small, dependency-free client for the e-Stat REST API 3.0."""

from __future__ import annotations

import json
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class EstatApiError(RuntimeError):
    """Raised when e-Stat returns an HTTP, transport, or API-level error."""


OpenUrl = Callable[..., Any]


def _verified_ssl_context() -> ssl.SSLContext:
    """Build a verified TLS context, including the macOS system CA fallback."""
    default_paths = ssl.get_default_verify_paths()
    if default_paths.cafile:
        return ssl.create_default_context()
    system_ca = Path("/etc/ssl/cert.pem")
    if system_ca.is_file():
        return ssl.create_default_context(cafile=str(system_ca))
    return ssl.create_default_context()


@dataclass(frozen=True)
class EstatClient:
    """Client for the JSON endpoints of e-Stat API version 3.0."""

    app_id: str
    timeout_seconds: float = 30.0
    max_attempts: int = 3
    retry_delay_seconds: float = 1.0
    base_url: str = "https://api.e-stat.go.jp/rest/3.0/app/json"
    opener: OpenUrl = urlopen

    def get_stats_list(
        self,
        *,
        search_word: str | None = None,
        stats_code: str | None = None,
        survey_years: str | None = None,
        limit: int = 100,
        start_position: int = 1,
    ) -> dict[str, Any]:
        """Search available statistical tables."""
        params: dict[str, str | int] = {
            "limit": limit,
            "startPosition": start_position,
        }
        if search_word:
            params["searchWord"] = search_word
        if stats_code:
            params["statsCode"] = stats_code
        if survey_years:
            params["surveyYears"] = survey_years
        return self._get(
            "getStatsList",
            params,
            root_key="GET_STATS_LIST",
        )

    def get_meta_info(self, *, stats_data_id: str) -> dict[str, Any]:
        """Fetch dimensions and classification codes for a statistical table."""
        return self._get(
            "getMetaInfo",
            {"statsDataId": stats_data_id},
            root_key="GET_META_INFO",
        )

    def get_stats_data(
        self,
        *,
        stats_data_id: str,
        filters: Mapping[str, str] | None = None,
        limit: int = 100_000,
        start_position: int = 1,
    ) -> dict[str, Any]:
        """Fetch values for a statistical table with optional e-Stat filters."""
        params: dict[str, str | int] = {
            "statsDataId": stats_data_id,
            "limit": limit,
            "startPosition": start_position,
            "metaGetFlg": "Y",
            "cntGetFlg": "N",
            "explanationGetFlg": "Y",
            "annotationGetFlg": "Y",
        }
        if filters:
            params.update(filters)
        return self._get("getStatsData", params, root_key="GET_STATS_DATA")

    def _get(
        self,
        endpoint: str,
        params: Mapping[str, str | int],
        *,
        root_key: str,
    ) -> dict[str, Any]:
        query = urlencode({"appId": self.app_id, **params})
        url = f"{self.base_url}/{endpoint}?{query}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "hotel-supply-demand-etl/0.1",
            },
        )

        for attempt in range(1, self.max_attempts + 1):
            try:
                with self.opener(
                    request,
                    timeout=self.timeout_seconds,
                    context=_verified_ssl_context(),
                ) as response:
                    payload = json.load(response)
                break
            except HTTPError as exc:
                if exc.code < 500 or attempt == self.max_attempts:
                    raise EstatApiError(f"e-Stat HTTP error: {exc.code}") from exc
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                if attempt == self.max_attempts:
                    detail = type(exc).__name__
                    if isinstance(exc, URLError) and exc.reason:
                        detail = f"{detail}: {type(exc.reason).__name__}"
                    raise EstatApiError(
                        f"Failed to receive a valid response from e-Stat ({detail})"
                    ) from exc
            time.sleep(self.retry_delay_seconds * attempt)
        else:  # pragma: no cover - the loop either breaks or raises
            raise EstatApiError("e-Stat request failed")

        if not isinstance(payload, dict) or root_key not in payload:
            raise EstatApiError(f"Unexpected e-Stat response: missing {root_key}")

        status = payload[root_key].get("RESULT", {})
        status_code = status.get("STATUS")
        if status_code not in (0, "0"):
            message = status.get("ERROR_MSG", "Unknown e-Stat API error")
            raise EstatApiError(f"e-Stat API error {status_code}: {message}")

        return payload
