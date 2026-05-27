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

    def _headers(self, idempotency_key: str | None,
                  client_token: str | None = None) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "legichain-sdk-python/0.1.0",
        }
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key
        if client_token:
            h["X-KYC-Client-Token"] = client_token
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
                 params: dict | None = None,
                 client_token: str | None = None) -> Any:
        client = getattr(self, "_client", None) or httpx.Client(timeout=self.timeout)
        try:
            resp = client.request(
                method, f"{self.base_url}{path}",
                json=json, params=params,
                headers=self._headers(idem, client_token=client_token),
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

    # ── KYC — application lifecycle ──────────────────────────────────
    # Server-side semantics: this SDK does NOT read NFC chips. Take
    # raw bytes from a mobile client (which uses the iOS/Android/Flutter
    # /React-Native SDK to read the chip) and forward them here.

    def kyc_create_application(self, *,
        subject_external_id: str | None = None,
        persona_id: str | None = None,
        external_reference: str | None = None,
        intent: str = "onboarding",
        document_type_allowed: list[str] | None = None,
        nfc_required: bool = False,
        callback_url: str | None = None,
        claimed_full_name: str | None = None,
        claimed_personal_number: str | None = None,
        claimed_birth_date: str | None = None,
        claimed_expiry_date: str | None = None,
        claimed_document_number: str | None = None,
        claimed_nationality: str | None = None,
        claimed_issuing_country: str | None = None,
        claimed_sex: str | None = None,
        claimed_document_type: str | None = None,
        meta: dict[str, Any] | None = None,
        idem: str | None = None,
    ) -> dict[str, Any]:
        """Create a KYC application. Returns ids + a short-lived
        `client_token` for per-artefact endpoints."""
        body: dict[str, Any] = {
            "intent": intent,
            "document_type_allowed": document_type_allowed or ["tr_id_card", "passport"],
            "nfc_required": nfc_required,
            "meta": meta or {},
        }
        for k, v in {
            "subject_external_id": subject_external_id,
            "persona_id": persona_id,
            "external_reference": external_reference,
            "callback_url": callback_url,
            "claimed_full_name": claimed_full_name,
            "claimed_personal_number": claimed_personal_number,
            "claimed_birth_date": claimed_birth_date,
            "claimed_expiry_date": claimed_expiry_date,
            "claimed_document_number": claimed_document_number,
            "claimed_nationality": claimed_nationality,
            "claimed_issuing_country": claimed_issuing_country,
            "claimed_sex": claimed_sex,
            "claimed_document_type": claimed_document_type,
        }.items():
            if v is not None:
                body[k] = v
        return self._request("POST", "/v1/kyc/applications", json=body, idem=idem)

    def kyc_status(self, application_id: str, *,
                    include_extracted: bool = False) -> dict[str, Any]:
        return self._request("GET",
            f"/v1/kyc/applications/{application_id}/status",
            params={"include_extracted": "true"} if include_extracted else None)

    def kyc_upload_document(self, application_id: str, *,
        client_token: str,
        document_type: str,
        side: str,
        image_b64: str,
        mime_type: str = "image/jpeg",
        captured_at: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "document_type": document_type, "side": side,
            "mime_type": mime_type, "image_b64": image_b64,
        }
        if captured_at:
            body["captured_at_client"] = captured_at
        return self._request("POST",
            f"/v1/kyc/applications/{application_id}/documents",
            json=body, client_token=client_token)

    def kyc_submit_nfc(self, application_id: str, *,
        client_token: str,
        protocol: str,                # 'BAC' or 'PACE'
        sod_b64: str,
        key_derivation: str | None = None,
        dg1_b64: str | None = None, dg2_b64: str | None = None,
        dg11_b64: str | None = None, dg14_b64: str | None = None,
        dg15_b64: str | None = None,
        active_authentication_b64: str | None = None,
    ) -> dict[str, Any]:
        """Forward an NFC chip read produced by a mobile client.
        This SDK never reads chips directly — pass through the base64
        SOD + DG bytes the mobile SDK extracted."""
        body: dict[str, Any] = {
            "protocol": protocol, "access_error": False, "sod_b64": sod_b64,
        }
        for k, v in [
            ("key_derivation", key_derivation),
            ("dg1_b64", dg1_b64), ("dg2_b64", dg2_b64),
            ("dg11_b64", dg11_b64), ("dg14_b64", dg14_b64),
            ("dg15_b64", dg15_b64),
            ("active_authentication_b64", active_authentication_b64),
        ]:
            if v is not None:
                body[k] = v
        return self._request("POST",
            f"/v1/kyc/applications/{application_id}/nfc",
            json=body, client_token=client_token)

    def kyc_nfc_access_error(self, application_id: str, *,
        client_token: str,
        protocol: str = "PACE",
        code: str = "chip_not_responding",
    ) -> dict[str, Any]:
        """Mobile reports the chip read failed (antenna noise, CAN
        required, …). Server keeps state at `awaiting_nfc` — no attempt
        burned."""
        return self._request("POST",
            f"/v1/kyc/applications/{application_id}/nfc",
            json={"protocol": protocol, "access_error": True,
                  "access_error_code": code},
            client_token=client_token)

    def kyc_upload_selfie(self, application_id: str, *,
        client_token: str, image_b64: str,
        mime_type: str = "image/jpeg", is_video: bool = False,
    ) -> dict[str, Any]:
        return self._request("POST",
            f"/v1/kyc/applications/{application_id}/selfie",
            json={"mime_type": mime_type, "image_b64": image_b64,
                  "is_video": is_video},
            client_token=client_token)

    def kyc_liveness_challenge(self, application_id: str, *,
        client_token: str, length: int = 3, ttl_seconds: int = 60,
    ) -> dict[str, Any]:
        return self._request("POST",
            f"/v1/kyc/applications/{application_id}/liveness/challenge",
            json={"length": length, "ttl_seconds": ttl_seconds},
            client_token=client_token)

    def kyc_submit_liveness(self, application_id: str, *,
        client_token: str,
        challenge_token: str,
        actions_performed: list[str],
        frames_b64: list[str] | None = None,
        pad_score: float | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "challenge_token": challenge_token,
            "actions_performed": actions_performed,
        }
        if frames_b64 is not None:
            body["frames_b64"] = frames_b64
        if pad_score is not None:
            body["pad_score"] = pad_score
        return self._request("POST",
            f"/v1/kyc/applications/{application_id}/liveness",
            json=body, client_token=client_token)

    def kyc_submit(self, application_id: str, *,
                    client_token: str) -> dict[str, Any]:
        """Trigger the decision. Idempotent."""
        return self._request("POST",
            f"/v1/kyc/applications/{application_id}/submit",
            json={}, client_token=client_token)

    def kyc_retry(self, application_id: str, *,
                   client_token: str, reason: str | None = None) -> dict[str, Any]:
        return self._request("POST",
            f"/v1/kyc/applications/{application_id}/retry",
            json={"reason": reason} if reason else {},
            client_token=client_token)

    def kyc_extend_ttl(self, application_id: str, *,
                        client_token: str) -> dict[str, Any]:
        return self._request("POST",
            f"/v1/kyc/applications/{application_id}/extend-ttl",
            json={}, client_token=client_token)

    # ── KYC tenant admin (compliance officer) ───────────────────────
    def kyc_admin_list(self, *, state: str | None = None,
                        intent: str | None = None,
                        persona_id: str | None = None,
                        limit: int = 50,
                        cursor: str | None = None) -> dict[str, Any]:
        params = {"limit": limit}
        for k, v in {"state": state, "intent": intent,
                      "persona_id": persona_id, "cursor": cursor}.items():
            if v is not None:
                params[k] = v
        return self._request("GET", "/v1/admin/kyc/applications", params=params)

    def kyc_admin_detail(self, application_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/admin/kyc/applications/{application_id}")

    def kyc_admin_approve(self, application_id: str, *,
                           notes: str | None = None,
                           reset_risk: bool = False) -> dict[str, Any]:
        return self._request("POST",
            f"/v1/admin/kyc/applications/{application_id}/approve",
            json={"notes": notes, "reset_risk": reset_risk})

    def kyc_admin_reject(self, application_id: str, *, reason_code: str,
                          notes: str | None = None) -> dict[str, Any]:
        body = {"reason_code": reason_code}
        if notes:
            body["notes"] = notes
        return self._request("POST",
            f"/v1/admin/kyc/applications/{application_id}/reject", json=body)

    def kyc_admin_request_retry(self, application_id: str, *,
                                 notes: str | None = None) -> dict[str, Any]:
        return self._request("POST",
            f"/v1/admin/kyc/applications/{application_id}/request-retry",
            json={"notes": notes} if notes else {})

    # ── Address Verification ────────────────────────────────────────
    def av_create(self, *, claimed_address: dict[str, Any],
                    subject_external_id: str | None = None,
                    persona_id: str | None = None,
                    accepted_document_types: list[str] | None = None,
                    max_age_days: int = 90,
                    callback_url: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "claimed_address": claimed_address,
            "accepted_document_types": accepted_document_types or
                ["utility_bill", "bank_statement"],
            "max_age_days": max_age_days,
        }
        for k, v in {"subject_external_id": subject_external_id,
                      "persona_id": persona_id,
                      "callback_url": callback_url}.items():
            if v is not None:
                body[k] = v
        return self._request("POST", "/v1/address-verifications", json=body)

    def av_upload_proof(self, verification_id: str, *,
                         client_token: str,
                         document_type: str,
                         mime_type: str,
                         image_b64: str,
                         captured_at: str | None = None) -> dict[str, Any]:
        body = {
            "document_type": document_type, "mime_type": mime_type,
            "image_b64": image_b64,
        }
        if captured_at:
            body["captured_at_client"] = captured_at
        return self._request("POST",
            f"/v1/address-verifications/{verification_id}/proof",
            json=body, client_token=client_token)

    def av_submit(self, verification_id: str, *,
                   client_token: str) -> dict[str, Any]:
        return self._request("POST",
            f"/v1/address-verifications/{verification_id}/submit",
            json={}, client_token=client_token)

    def av_status(self, verification_id: str) -> dict[str, Any]:
        return self._request("GET",
            f"/v1/address-verifications/{verification_id}/status")

    # ── Personas ────────────────────────────────────────────────────
    def persona_create(self, *, subject_external_id: str | None = None,
                        display_name: str | None = None,
                        meta: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if subject_external_id:
            body["subject_external_id"] = subject_external_id
        if display_name:
            body["display_name"] = display_name
        if meta:
            body["meta"] = meta
        return self._request("POST", "/v1/personas", json=body)

    def persona_list(self, *, subject_external_id: str | None = None,
                      limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if subject_external_id:
            params["subject_external_id"] = subject_external_id
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/v1/personas", params=params)

    def persona_get(self, persona_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/personas/{persona_id}")


class AsyncLegichain(_BaseClient):
    """Asyncio client. Use as async context manager."""

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, *,
                       json: Any | None = None, idem: str | None = None,
                       params: dict | None = None,
                       client_token: str | None = None) -> Any:
        resp = await self._client.request(
            method, f"{self.base_url}{path}",
            json=json, params=params,
            headers=self._headers(idem, client_token=client_token),
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

    # ── KYC (async equivalents) ─────────────────────────────────────
    async def kyc_create_application(self, *,
        subject_external_id: str | None = None,
        persona_id: str | None = None,
        external_reference: str | None = None,
        intent: str = "onboarding",
        document_type_allowed: list[str] | None = None,
        nfc_required: bool = False,
        callback_url: str | None = None,
        claimed_full_name: str | None = None,
        claimed_personal_number: str | None = None,
        claimed_birth_date: str | None = None,
        claimed_expiry_date: str | None = None,
        claimed_document_number: str | None = None,
        claimed_nationality: str | None = None,
        claimed_issuing_country: str | None = None,
        claimed_sex: str | None = None,
        claimed_document_type: str | None = None,
        meta: dict[str, Any] | None = None,
        idem: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "intent": intent,
            "document_type_allowed": document_type_allowed or ["tr_id_card", "passport"],
            "nfc_required": nfc_required,
            "meta": meta or {},
        }
        for k, v in {
            "subject_external_id": subject_external_id,
            "persona_id": persona_id,
            "external_reference": external_reference,
            "callback_url": callback_url,
            "claimed_full_name": claimed_full_name,
            "claimed_personal_number": claimed_personal_number,
            "claimed_birth_date": claimed_birth_date,
            "claimed_expiry_date": claimed_expiry_date,
            "claimed_document_number": claimed_document_number,
            "claimed_nationality": claimed_nationality,
            "claimed_issuing_country": claimed_issuing_country,
            "claimed_sex": claimed_sex,
            "claimed_document_type": claimed_document_type,
        }.items():
            if v is not None:
                body[k] = v
        return await self._request("POST", "/v1/kyc/applications", json=body, idem=idem)

    async def kyc_status(self, application_id: str, *,
                          include_extracted: bool = False) -> dict[str, Any]:
        return await self._request("GET",
            f"/v1/kyc/applications/{application_id}/status",
            params={"include_extracted": "true"} if include_extracted else None)

    async def kyc_upload_document(self, application_id: str, *,
        client_token: str, document_type: str, side: str, image_b64: str,
        mime_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/kyc/applications/{application_id}/documents",
            json={"document_type": document_type, "side": side,
                  "mime_type": mime_type, "image_b64": image_b64},
            client_token=client_token)

    async def kyc_submit_nfc(self, application_id: str, *,
        client_token: str, protocol: str, sod_b64: str,
        key_derivation: str | None = None,
        dg1_b64: str | None = None, dg2_b64: str | None = None,
        dg11_b64: str | None = None, dg14_b64: str | None = None,
        dg15_b64: str | None = None,
        active_authentication_b64: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "protocol": protocol, "access_error": False, "sod_b64": sod_b64,
        }
        for k, v in [
            ("key_derivation", key_derivation),
            ("dg1_b64", dg1_b64), ("dg2_b64", dg2_b64),
            ("dg11_b64", dg11_b64), ("dg14_b64", dg14_b64),
            ("dg15_b64", dg15_b64),
            ("active_authentication_b64", active_authentication_b64),
        ]:
            if v is not None:
                body[k] = v
        return await self._request("POST",
            f"/v1/kyc/applications/{application_id}/nfc",
            json=body, client_token=client_token)

    async def kyc_nfc_access_error(self, application_id: str, *,
        client_token: str, protocol: str = "PACE",
        code: str = "chip_not_responding",
    ) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/kyc/applications/{application_id}/nfc",
            json={"protocol": protocol, "access_error": True,
                  "access_error_code": code},
            client_token=client_token)

    async def kyc_upload_selfie(self, application_id: str, *,
        client_token: str, image_b64: str,
        mime_type: str = "image/jpeg", is_video: bool = False,
    ) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/kyc/applications/{application_id}/selfie",
            json={"mime_type": mime_type, "image_b64": image_b64,
                  "is_video": is_video},
            client_token=client_token)

    async def kyc_liveness_challenge(self, application_id: str, *,
        client_token: str, length: int = 3, ttl_seconds: int = 60,
    ) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/kyc/applications/{application_id}/liveness/challenge",
            json={"length": length, "ttl_seconds": ttl_seconds},
            client_token=client_token)

    async def kyc_submit_liveness(self, application_id: str, *,
        client_token: str, challenge_token: str,
        actions_performed: list[str],
        frames_b64: list[str] | None = None,
        pad_score: float | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "challenge_token": challenge_token,
            "actions_performed": actions_performed,
        }
        if frames_b64 is not None:
            body["frames_b64"] = frames_b64
        if pad_score is not None:
            body["pad_score"] = pad_score
        return await self._request("POST",
            f"/v1/kyc/applications/{application_id}/liveness",
            json=body, client_token=client_token)

    async def kyc_submit(self, application_id: str, *,
                          client_token: str) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/kyc/applications/{application_id}/submit",
            json={}, client_token=client_token)

    async def kyc_retry(self, application_id: str, *,
                         client_token: str,
                         reason: str | None = None) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/kyc/applications/{application_id}/retry",
            json={"reason": reason} if reason else {},
            client_token=client_token)

    async def kyc_extend_ttl(self, application_id: str, *,
                              client_token: str) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/kyc/applications/{application_id}/extend-ttl",
            json={}, client_token=client_token)

    async def kyc_admin_list(self, *, state: str | None = None,
                              intent: str | None = None,
                              limit: int = 50,
                              cursor: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if state:
            params["state"] = state
        if intent:
            params["intent"] = intent
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/v1/admin/kyc/applications",
                                     params=params)

    async def kyc_admin_detail(self, application_id: str) -> dict[str, Any]:
        return await self._request("GET",
            f"/v1/admin/kyc/applications/{application_id}")

    async def kyc_admin_approve(self, application_id: str, *,
                                 notes: str | None = None,
                                 reset_risk: bool = False) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/admin/kyc/applications/{application_id}/approve",
            json={"notes": notes, "reset_risk": reset_risk})

    async def kyc_admin_reject(self, application_id: str, *, reason_code: str,
                                notes: str | None = None) -> dict[str, Any]:
        body = {"reason_code": reason_code}
        if notes:
            body["notes"] = notes
        return await self._request("POST",
            f"/v1/admin/kyc/applications/{application_id}/reject", json=body)

    async def kyc_admin_request_retry(self, application_id: str, *,
                                       notes: str | None = None) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/admin/kyc/applications/{application_id}/request-retry",
            json={"notes": notes} if notes else {})

    # ── Address Verification (async) ────────────────────────────────
    async def av_create(self, *, claimed_address: dict[str, Any],
                         subject_external_id: str | None = None,
                         persona_id: str | None = None,
                         accepted_document_types: list[str] | None = None,
                         max_age_days: int = 90,
                         callback_url: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "claimed_address": claimed_address,
            "accepted_document_types": accepted_document_types or
                ["utility_bill", "bank_statement"],
            "max_age_days": max_age_days,
        }
        for k, v in {"subject_external_id": subject_external_id,
                      "persona_id": persona_id,
                      "callback_url": callback_url}.items():
            if v is not None:
                body[k] = v
        return await self._request("POST", "/v1/address-verifications", json=body)

    async def av_upload_proof(self, verification_id: str, *,
                               client_token: str, document_type: str,
                               mime_type: str, image_b64: str) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/address-verifications/{verification_id}/proof",
            json={"document_type": document_type, "mime_type": mime_type,
                  "image_b64": image_b64},
            client_token=client_token)

    async def av_submit(self, verification_id: str, *,
                         client_token: str) -> dict[str, Any]:
        return await self._request("POST",
            f"/v1/address-verifications/{verification_id}/submit",
            json={}, client_token=client_token)

    async def av_status(self, verification_id: str) -> dict[str, Any]:
        return await self._request("GET",
            f"/v1/address-verifications/{verification_id}/status")

    # ── Personas (async) ────────────────────────────────────────────
    async def persona_create(self, *,
                              subject_external_id: str | None = None,
                              display_name: str | None = None,
                              meta: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if subject_external_id:
            body["subject_external_id"] = subject_external_id
        if display_name:
            body["display_name"] = display_name
        if meta:
            body["meta"] = meta
        return await self._request("POST", "/v1/personas", json=body)

    async def persona_list(self, *, subject_external_id: str | None = None,
                            limit: int = 50,
                            cursor: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if subject_external_id:
            params["subject_external_id"] = subject_external_id
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/v1/personas", params=params)

    async def persona_get(self, persona_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/personas/{persona_id}")
