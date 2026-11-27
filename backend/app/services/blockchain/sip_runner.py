"""Triggers vault SIPs on their day (Phase 10, B16).

A SIP is rule-based: no AI, no evidence. `runSip` is open to anyone and
takes no arguments; the vault itself checks the date, amount, end, price
age and slippage. This runner only saves owners from doing it by hand, with
its own key (BLOCKCHAIN_SIP_RUNNER_PRIVATE_KEY), not the relayer's.
"""

import logging

from app.data.collections import get_wallet_links_collection
from app.services.blockchain.client import ChainClient

logger = logging.getLogger(__name__)

MAX_PER_CYCLE = 20


async def run_due_sips(client: ChainClient) -> int:
    """Runs every due SIP of a linked wallet's vault; returns how many ran."""
    now = await client.now()
    ran = 0
    async for link in get_wallet_links_collection().find({}, {"address": 1}):
        if ran >= MAX_PER_CYCLE:
            break
        vault_address = await client.vault_of(link["address"])
        if vault_address is None:
            continue
        vault = client.vault(vault_address)
        _fund, amount, _slippage, _day, next_run, end = await vault.functions.sip().call()
        if amount == 0 or now < next_run or now > end:
            continue
        try:
            await client.send(vault.functions.runSip(), role="sip_runner")
            ran += 1
        except Exception as exc:  # noqa: BLE001 - e.g. stale price or too little tINR; retried next cycle
            logger.info("SIP for vault %s not run: %s", vault_address, type(exc).__name__)
    return ran
