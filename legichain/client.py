"""Sync + async clients for the Legichain API."""

from __future__ import annotations

import secrets
from typing import Any, Self

import httpx


class LegichainError(Exception):
    """Raised on any non-2xx API response. Carries the Problem Details body."""

    def __init__(self, status_code: int, problem: dict[str, Any]) -> None:
        self.status_code = status_code
        self.code = problem.get("code", "")
        self.title = problem.get("title", "")
        self.detail = problem.get("detail", "")
        self.problem = problem
        super().__init__(f"{status_code} {self.code}: {self.detail}")


def _idem() -> str:
    return secrets.token_hex(16)


class _BaseClient:
    def __init__(self, api_key: str, base_url: str = "https://api.legichain.com",
                 timeout: float = 30.0) -> None:
        if "." not in api_key:
            raise ValueError("api_key must be 'key_id.secret'")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self, idempotency_key: str | None) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "legichain-sdk-python/0.1.0",
        }
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key
        return h


class Legichain(_BaseClient):
    """Synchronous client."""

    def __enter__(self) -> Self:
        self._client = httpx.Client(timeout=self.timeout)
        return self

    def __exit__(self, *exc: Any) -> None:
        self._client.close()

    def _request(self, method: str, path: str, *,
                 json: Any | None = None, idem: str | None = None,
                 params: dict | None = None) -> Any:
        client = getattr(self, "_client", None) or httpx.Client(timeout=self.timeout)
        try:
            resp = client.request(
                method, f"{self.base_url}{path}",
                json=json, params=params,
                headers=self._headers(idem),
            )
        finally:
            if not hasattr(self, "_client"):
                client.close()
        if not 200 <= resp.status_code < 300:
            try:
                problem = resp.json()
            except Exception:
                problem = {"detail": resp.text[:400]}
            raise LegichainError(resp.status_code, problem)
        if resp.headers.get("content-type", "").startswith("application/pdf"):
            return resp.content
        return resp.json()

    # ── Screening ─────────────────────────────────────────────────────
    def screen_person(self, *, name: str, country: str | None = None,
                       dob: str | None = None, document: str | None = None,
                       idem: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/v1/screen/person",
                              json={"name": name, "country": country,
                                    "dob": dob, "document": document},
                              idem=idem)

    def screen_company(self, *, name: str, country: str | None = None,
                       registration_number: str | None = None,
                       idem: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/v1/screen/company",
                              json={"name": name, "country": country,
                                    "registration_number": registration_number},
                              idem=idem)

    def screen_crypto(self, *, address: str, chain: str | None = None,
                       idem: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/v1/screen/crypto",
                              json={"address": address, "chain": chain}, idem=idem)

    def screen_batch(self, items: list[dict[str, Any]],
                     idem: str | None = None) -> list[dict[str, Any]]:
        return self._request("POST", "/v1/screen/batch",
                              json={"items": items}, idem=idem)

    def screen_batch_async(self, items: list[dict[str, Any]],
                            idem: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/v1/screen/batch/async",
                              json={"items": items}, idem=idem or _idem())

    def job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/screen/jobs/{job_id}")

    # ── Reports ───────────────────────────────────────────────────────
    def report_wallet(self, *, address: str, chain: str | None = None,
                       format: str = "json", refresh: bool = False) -> Any:
        return self._request("POST", "/v1/reports/wallet",
                              json={"address": address, "chain": chain,
                                    "format": format, "refresh": refresh})

    def report_person(self, *, name: str, country: str | None = None,
                       dob: str | None = None, document: str | None = None,
                       address: str | None = None,
                       gender: str | None = None,
                       format: str = "json") -> Any:
        return self._request("POST", "/v1/reports/person",
                              json={"name": name, "country": country,
                                    "dob": dob, "document": document,
                                    "address": address, "gender": gender,
                                    "format": format})

    def report_company(self, *, name: str, country: str | None = None,
                       registration_number: str | None = None,
                       incorporation_date: str | None = None,
                       address: str | None = None,
                       format: str = "json") -> Any:
        return self._request("POST", "/v1/reports/company",
                              json={"name": name, "country": country,
                                    "registration_number": registration_number,
                                    "incorporation_date": incorporation_date,
                                    "address": address, "format": format})

    # ── Admin ─────────────────────────────────────────────────────────
    def credits(self) -> dict[str, Any]:
        return self._request("GET", "/v1/admin/credits")

    def usage(self, cursor: str | None = None, limit: int = 50) -> dict[str, Any]:
        return self._request("GET", "/v1/admin/usage",
                              params={"cursor": cursor, "limit": limit})

    def status(self) -> dict[str, Any]:
        """Public status endpoint — no auth required."""
        return self._request("GET", "/v1/status")


class AsyncLegichain(_BaseClient):
    """Asyncio client. Use as async context manager."""

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, *,
                       json: Any | None = None, idem: str | None = None,
                       params: dict | None = None) -> Any:
        resp = await self._client.request(
            method, f"{self.base_url}{path}",
            json=json, params=params, headers=self._headers(idem),
        )
        if not 200 <= resp.status_code < 300:
            try:
                problem = resp.json()
            except Exception:
                problem = {"detail": resp.text[:400]}
            raise LegichainError(resp.status_code, problem)
        if resp.headers.get("content-type", "").startswith("application/pdf"):
            return resp.content
        return resp.json()

    # async clones of the sync methods omitted for brevity — same payloads.
    async def screen_crypto(self, *, address: str, chain: str | None = None,
                              idem: str | None = None) -> dict[str, Any]:
        return await self._request("POST", "/v1/screen/crypto",
                                     json={"address": address, "chain": chain},
                                     idem=idem)

    async def screen_person(self, *, name: str, country: str | None = None,
                              dob: str | None = None, document: str | None = None,
                              idem: str | None = None) -> dict[str, Any]:
        return await self._request("POST", "/v1/screen/person",
                                     json={"name": name, "country": country,
                                           "dob": dob, "document": document},
                                     idem=idem)

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/v1/status")
