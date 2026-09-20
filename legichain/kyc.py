"""Typed v2 evidence APIs for backend integrations.

Keep the same idempotency key and body when retrying an uncertain upload.
Operation completion means processing finished; it is not a KYC approval.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel

from .kyc_models import (
    DocumentSubmitRequest, KYCApplicationCreateRequest, LivenessSubmitRequest,
    NFCSubmitRequest, SelfieSubmitRequest,
)

EvidenceStep = Literal["documents", "selfie", "nfc", "liveness"]
_MODELS = {"documents": DocumentSubmitRequest, "selfie": SelfieSubmitRequest,
           "nfc": NFCSubmitRequest, "liveness": LivenessSubmitRequest}


def evidence_body(step: EvidenceStep, body: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if step not in _MODELS:
        raise ValueError("Unsupported KYC evidence step")
    value = body.model_dump(mode="json") if isinstance(body, BaseModel) else body
    return _MODELS[step].model_validate(value).model_dump(mode="json", exclude_none=True)


class OperationFailed(RuntimeError):
    def __init__(self, operation: dict[str, Any]):
        self.operation = operation
        super().__init__(f"KYC operation {operation.get('id')} {operation['status']}: "
                         f"{operation.get('error_code') or 'no error code'}")


def _terminal(operation: dict[str, Any]) -> bool:
    if operation["status"] in {"failed", "expired", "cancelled"}:
        raise OperationFailed(operation)
    return operation["status"] == "completed"


class KycV2:
    def __init__(self, client):
        self._client = client

    def start(self, body: KYCApplicationCreateRequest | dict[str, Any], *, idem: str):
        from .kyc_session import KycSession
        return KycSession(self, self.create(body, idem=idem))

    def create(self, body: KYCApplicationCreateRequest | dict[str, Any], *, idem: str):
        from .client import _v2_key
        value = KYCApplicationCreateRequest.model_validate(body).model_dump(mode="json", exclude_none=True)
        return self._client._request("POST", "/v1/kyc/applications", json=value, idem=_v2_key(idem))

    def evidence(self, application_id: str, client_token: str, step: EvidenceStep,
                 body: BaseModel | dict[str, Any], *, idem: str):
        return self._client.enqueue_kyc_evidence(application_id, step, evidence_body(step, body),
                                                 idem=idem, client_token=client_token)

    def challenge(self, application_id: str, client_token: str, *, length=3, ttl_seconds=120):
        return self._client.kyc_liveness_challenge(application_id, client_token=client_token,
                                                  length=length, ttl_seconds=ttl_seconds)

    def wait(self, operation_id: str, *, timeout: float = 120, interval: float = 1):
        if timeout <= 0 or interval <= 0:
            raise ValueError("timeout and interval must be positive")
        deadline = time.monotonic() + timeout
        while True:
            operation = self._client.operation(operation_id)
            if _terminal(operation):
                return operation
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Operation {operation_id} is still processing; keep its receipt")
            time.sleep(min(interval, remaining))

    def submit(self, application_id: str, client_token: str, *, operations: list[str]):
        """Require completed evidence operations before recording submission.

        Persist receipts in your own session store. Pass all operation IDs for
        this attempt. A network failure here does not imply submission failed;
        reconcile application status before repeating it.
        """
        for identifier in operations:
            if not _terminal(self._client.operation(identifier)):
                raise RuntimeError("Evidence is still processing; wait before submitting")
        return self._client._request("POST", f"/v1/kyc/applications/{quote(application_id, safe='')}/submit",
                                     json={}, client_token=client_token)


class AsyncKycV2:
    def __init__(self, client):
        self._client = client

    async def start(self, body: KYCApplicationCreateRequest | dict[str, Any], *, idem: str):
        from .kyc_session import AsyncKycSession
        return AsyncKycSession(self, await self.create(body, idem=idem))

    async def create(self, body: KYCApplicationCreateRequest | dict[str, Any], *, idem: str):
        from .client import _v2_key
        value = KYCApplicationCreateRequest.model_validate(body).model_dump(mode="json", exclude_none=True)
        return await self._client._request("POST", "/v1/kyc/applications", json=value, idem=_v2_key(idem))

    async def evidence(self, application_id: str, client_token: str, step: EvidenceStep,
                       body: BaseModel | dict[str, Any], *, idem: str):
        return await self._client.enqueue_kyc_evidence(application_id, step, evidence_body(step, body),
                                                       idem=idem, client_token=client_token)

    async def challenge(self, application_id: str, client_token: str, *, length=3, ttl_seconds=120):
        return await self._client.kyc_liveness_challenge(application_id, client_token=client_token,
                                                        length=length, ttl_seconds=ttl_seconds)

    async def wait(self, operation_id: str, *, timeout: float = 120, interval: float = 1):
        if timeout <= 0 or interval <= 0:
            raise ValueError("timeout and interval must be positive")
        deadline = time.monotonic() + timeout
        while True:
            operation = await self._client.operation(operation_id)
            if _terminal(operation):
                return operation
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Operation {operation_id} is still processing; keep its receipt")
            await asyncio.sleep(min(interval, remaining))

    async def submit(self, application_id: str, client_token: str, *, operations: list[str]):
        for identifier in operations:
            if not _terminal(await self._client.operation(identifier)):
                raise RuntimeError("Evidence is still processing; wait before submitting")
        return await self._client._request("POST", f"/v1/kyc/applications/{quote(application_id, safe='')}/submit",
                                           json={}, client_token=client_token)
