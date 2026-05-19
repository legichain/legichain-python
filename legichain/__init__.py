"""Official Python SDK for the Legichain AML API.

Usage:
    from legichain import Legichain
    cli = Legichain(api_key="lc_live_abc.sk_live_xyz", base_url="https://api.legichain.com")
    result = cli.screen_crypto(address="0x...", chain="ETH")
    if result["matched"]:
        print(result["hits"][0]["risk_score"])

Async variant:
    from legichain import AsyncLegichain
    async with AsyncLegichain(api_key=...) as cli:
        result = await cli.screen_crypto(...)

Webhook verification (server-side):
    from legichain.webhooks import verify_signature
    if not verify_signature(request.body, request.headers["Legichain-Signature"], secret):
        return 400
"""

from legichain.client import AsyncLegichain, Legichain, LegichainError
from legichain.webhooks import verify_signature

__all__ = ["Legichain", "AsyncLegichain", "LegichainError", "verify_signature"]
__version__ = "0.1.0"
