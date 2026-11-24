from typing import Any
from urllib.parse import urljoin

import httpx

from .config import settings


class KeitaroError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        self.status_code = status_code
        super().__init__(message)


class KeitaroClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.keitaro_base_url).rstrip("/") + "/"
        self.api_key = settings.api_key if api_key is None else api_key

    def request(self, method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
        if not self.api_key:
            raise KeitaroError("API_KEY не задан. Заполните локальный .env.", 503)
        url = urljoin(self.base_url, path.lstrip("/"))
        try:
            response = httpx.request(
                method,
                url,
                headers={"Api-Key": self.api_key},
                params=params,
                json=json,
                timeout=20.0,
            )
        except httpx.RequestError as exc:
            # Do not include request headers or credentials in the error text.
            raise KeitaroError(f"Не удалось связаться со стендом Keitaro: {type(exc).__name__}") from exc
        if response.is_error:
            detail = response.text[:500]
            raise KeitaroError(f"Keitaro вернул HTTP {response.status_code}: {detail}", response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise KeitaroError("Keitaro вернул некорректный JSON") from exc

    def get_campaigns(self, offset: int = 0, limit: int = 100) -> list[dict]:
        return self.request("GET", "/campaigns", params={"offset": offset, "limit": limit})

    def get_campaign(self, campaign_id: int) -> dict:
        return self.request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: dict) -> dict:
        return self.request("POST", "/campaigns", json=payload)

    def get_streams(self, campaign_id: int) -> list[dict]:
        return self.request("GET", f"/campaigns/{campaign_id}/streams")

    def get_stream(self, stream_id: int) -> dict:
        return self.request("GET", f"/streams/{stream_id}")

    def create_stream(self, payload: dict) -> dict:
        return self.request("POST", "/streams", json=payload)

    def update_stream(self, stream_id: int, payload: dict) -> dict:
        return self.request("PUT", f"/streams/{stream_id}", json=payload)

    def enable_campaign(self, campaign_id: int) -> dict:
        return self.request("POST", f"/campaigns/{campaign_id}/enable")

    def get_catalogs(self) -> dict:
        return {
            "offers": self.request("GET", "/offers"),
            "domains": self.request("GET", "/domains"),
            "groups": self.request("GET", "/groups", params={"type": "campaigns"}),
            "traffic_sources": self.request("GET", "/traffic_sources"),
        }
