"""Single-application helpers. The API token is the only configured credential."""
from __future__ import annotations


class KycSession:
    def __init__(self, api, created):
        self._api = api
        self.application_id = created["application_id"]
        self._token = created["client_token"]
        self._operations: set[str] = set()

    def evidence(self, step, body, *, idem: str):
        receipt = self._api.evidence(self.application_id, self._token, step, body, idem=idem)
        self._operations.add(receipt["operation_id"])
        return receipt

    def challenge(self, *, length=3, ttl_seconds=120):
        return self._api.challenge(self.application_id, self._token, length=length, ttl_seconds=ttl_seconds)

    def status(self):
        return self._api._client.kyc_status(self.application_id)

    def wait(self, operation_id, **options):
        if operation_id not in self._operations:
            raise ValueError("Operation does not belong to this SDK session")
        return self._api.wait(operation_id, **options)

    def submit(self):
        return self._api.submit(self.application_id, self._token, operations=list(self._operations))


class AsyncKycSession:
    def __init__(self, api, created):
        self._api = api
        self.application_id = created["application_id"]
        self._token = created["client_token"]
        self._operations: set[str] = set()

    async def evidence(self, step, body, *, idem: str):
        receipt = await self._api.evidence(self.application_id, self._token, step, body, idem=idem)
        self._operations.add(receipt["operation_id"])
        return receipt

    async def challenge(self, *, length=3, ttl_seconds=120):
        return await self._api.challenge(self.application_id, self._token, length=length, ttl_seconds=ttl_seconds)

    async def status(self):
        return await self._api._client.kyc_status(self.application_id)

    async def wait(self, operation_id, **options):
        if operation_id not in self._operations:
            raise ValueError("Operation does not belong to this SDK session")
        return await self._api.wait(operation_id, **options)

    async def submit(self):
        return await self._api.submit(self.application_id, self._token, operations=list(self._operations))
