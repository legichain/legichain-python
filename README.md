# Legichain Python SDK

Official Python client for the **Legichain** AML/sanctions/crypto-risk API.

```
pip install legichain-sdk
```

* Python 3.10+
* Sync and async clients (`Legichain`, `AsyncLegichain`)
* Webhook HMAC verification helper
* Typed Problem Details exceptions (RFC 7807)

---

## Quick start

```python
from legichain import Legichain

cli = Legichain(api_key="lc_live_xxxxxxxx.sk_live_xxxxxxxx")

# Screen a crypto wallet
result = cli.screen_crypto(address="0x6c0bD2BB04Fda9CBfeBb8DC1208Db32a0F8a4Edd", chain="ETH")
if result["matched"]:
    for hit in result["hits"]:
        print(hit["name"], hit["risk_level"], hit["risk_score"])

# Screen a natural person
result = cli.screen_person(name="Vladimir Putin", country="RU", dob="1952-10-07")

# Generate a PDF wallet report (returns raw bytes)
pdf = cli.report_wallet(address="0x...", chain="ETH", format="pdf")
with open("report.pdf", "wb") as f:
    f.write(pdf)

# Check remaining credits
print(cli.credits()["balance"])
```

### Async

```python
import asyncio
from legichain import AsyncLegichain

async def main():
    async with AsyncLegichain(api_key="lc_live_....sk_live_...") as cli:
        r = await cli.screen_crypto(address="0x...", chain="ETH")
        print(r)

asyncio.run(main())
```

### Error handling

Every non-2xx response is turned into a `LegichainError` carrying the
RFC 7807 Problem Details payload:

```python
from legichain import Legichain, LegichainError

cli = Legichain(api_key="...")
try:
    cli.screen_crypto(address="0xINVALID")
except LegichainError as e:
    print(e.status_code)        # 400
    print(e.code)               # "VAL_001_INVALID_ADDRESS"
    print(e.title)              # "Invalid address"
    print(e.detail)             # "Address fails checksum validation."
    print(e.problem["errors"])  # field-level errors, if any
```

### Idempotency

Mutating endpoints accept an `Idempotency-Key` header. The SDK exposes this
as the `idem=` argument. Replays within the 24 h cache window return the
same response body with header `Idempotent-Replay: true`.

```python
key = "checkout-2026-05-19-7f3c"
cli.screen_person(name="John Doe", idem=key)
cli.screen_person(name="John Doe", idem=key)  # served from cache
```

### Async batch screening

For batches above a few dozen items, prefer the async variant. The call
returns immediately with a `job_id`; the result is delivered to your
registered webhook endpoint **and** can be polled.

```python
job = cli.screen_batch_async([
    {"name": "John Doe", "country": "US"},
    {"address": "0xabc...", "chain": "ETH"},
])
print(job["id"], job["status"])     # queued

# Later (or via webhook screen.batch.completed):
done = cli.job(job["id"])
print(done["result"]["items"])
```

---

## Webhook verification

Set up an endpoint at `POST /v1/admin/webhooks` (via the dashboard or API)
and Legichain will send signed JSON events.

```python
from fastapi import FastAPI, Request, HTTPException
from legichain.webhooks import verify_signature

app = FastAPI()
SECRET = "whsec_..."   # shown once at endpoint creation

@app.post("/webhooks/legichain")
async def receive(req: Request):
    body = await req.body()
    sig = req.headers.get("Legichain-Signature", "")
    if not verify_signature(body, sig, SECRET):
        raise HTTPException(400, "Bad signature")
    payload = await req.json()
    if payload["event"] == "screen.batch.completed":
        ...
    return {"ok": True}
```

The verifier rejects requests older than 5 minutes by default (configurable
via `tolerance_sec=`).

---

## Reference

### `Legichain(api_key, base_url="https://api.legichain.com", timeout=30.0)`

Sync client. Use as a context manager to reuse a single underlying
`httpx.Client`:

```python
with Legichain(api_key="...") as cli:
    cli.screen_crypto(...)
    cli.screen_person(...)
```

### Screening

| Method | Endpoint |
| --- | --- |
| `screen_person(name, country, dob, document, idem)` | `POST /v1/screen/person` |
| `screen_company(name, country, registration_number, idem)` | `POST /v1/screen/company` |
| `screen_crypto(address, chain, idem)` | `POST /v1/screen/crypto` |
| `screen_batch(items, idem)` | `POST /v1/screen/batch` |
| `screen_batch_async(items, idem)` | `POST /v1/screen/batch/async` |
| `job(job_id)` | `GET /v1/screen/jobs/{id}` |

### Reports

| Method | Endpoint |
| --- | --- |
| `report_wallet(address, chain, format="json"|"pdf", refresh=False)` | `POST /v1/reports/wallet` |
| `report_person(name, country, dob, document, address, gender, format)` | `POST /v1/reports/person` |
| `report_company(name, country, registration_number, ...)` | `POST /v1/reports/company` |

When `format="pdf"` the client returns the raw PDF bytes.

### Admin / Account

| Method | Endpoint |
| --- | --- |
| `credits()` | `GET /v1/admin/credits` |
| `usage(cursor, limit)` | `GET /v1/admin/usage` |
| `status()` | `GET /v1/status` (no auth) |

---

## Key formats

Keys look like:

```
lc_live_<22>.sk_live_<44>     # production
lc_test_<22>.sk_test_<44>     # test mode — no credit charge, no webhooks fire
```

Test/dev keys cost zero credits and are safe to embed in CI.

---

## Versioning & support

The SDK follows the API version (`v1`). Breaking API changes ship under
`/v2/` with a deprecation window of at least 6 months for `/v1/`.

* Status page — <https://api.legichain.com/v1/status>
* Email — `support@legichain.com`
* GitHub — <https://github.com/legichain/legichain-python>
