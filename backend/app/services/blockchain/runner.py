"""Scheduled entry point for the worker, SIP runner and event reader (Phase 10).

Runs only when BLOCKCHAIN_ENABLED is true. One cycle: advance due tasks, run
due vault SIPs, then read new events. If the chain is down, the cycle logs
and the next one tries again; tasks keep their place.
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        from app.services.blockchain.client import ChainClient
        from app.services.blockchain.config import load_blockchain_config

        _client = ChainClient(load_blockchain_config(settings))
    return _client


async def run_cycle() -> None:
    from app.services.blockchain.events import sync_events
    from app.services.blockchain.sip_runner import run_due_sips
    from app.services.blockchain.worker import Worker, safe_error

    client = _get_client()
    try:
        await client.check_network()
        await Worker(client).run_due()
        await run_due_sips(client)
        await sync_events(client)
    except Exception as exc:  # noqa: BLE001 - chain or RPC down: try again next cycle
        logger.warning("Blockchain cycle skipped: %s", safe_error(exc, client.config.rpc_url))
