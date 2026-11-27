"""Wallet linking with a one-time signed message (Phase 10, B11).

The user signs a challenge in their wallet (EIP-191 `personal_sign`), which
proves they hold the key. Signing it costs nothing and moves nothing. Each
challenge works once and expires after a few minutes.
"""

import secrets
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.data import blockchain_repository as repo

CHALLENGE_MINUTES = 10


class WalletError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _checksum(address: str) -> str:
    from eth_utils import is_address, to_checksum_address

    if not is_address(address):
        raise WalletError(422, "Not a valid wallet address")
    return to_checksum_address(address)


def challenge_message(address: str, chain_id: int, nonce: str, expires_at: datetime) -> str:
    return (
        "IntelliVest wants to link this wallet to your account.\n"
        "Signing is free and does not move any funds.\n\n"
        f"Address: {address}\n"
        f"Chain ID: {chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Expires: {expires_at.isoformat()}"
    )


async def create_challenge(user_id: str, address: str, now: datetime | None = None) -> dict:
    address = _checksum(address)
    now = now or datetime.now(UTC)
    expires_at = (now + timedelta(minutes=CHALLENGE_MINUTES)).replace(microsecond=0)
    message = challenge_message(
        address, settings.blockchain_chain_id, secrets.token_hex(16), expires_at
    )
    await repo.put_challenge(user_id, address, message, expires_at)
    return {"message": message, "expires_at": expires_at}


async def verify_and_link(
    user_id: str, address: str, signature: str, now: datetime | None = None
) -> dict:
    from eth_account import Account
    from eth_account.messages import encode_defunct
    from eth_keys.exceptions import BadSignature

    address = _checksum(address)
    now = now or datetime.now(UTC)
    if await repo.get_wallet_link(user_id):
        raise WalletError(409, "Unlink your current wallet first")
    owner = await repo.get_wallet_link_by_address(address)
    if owner:
        raise WalletError(409, "This wallet is linked to another account")
    # Taken before checking the signature, so a failed attempt uses it up.
    challenge = await repo.take_challenge(user_id, address, now)
    if challenge is None:
        raise WalletError(400, "No live challenge for this wallet; request a new one")
    try:
        signer = Account.recover_message(
            encode_defunct(text=challenge["message"]), signature=bytes.fromhex(signature[2:])
        )
    except (BadSignature, ValueError, TypeError):
        raise WalletError(400, "Signature could not be read") from None
    if signer != address:
        raise WalletError(400, "Signature is not from this wallet")
    if not await repo.insert_wallet_link(user_id, address, now):
        raise WalletError(409, "Wallet already linked")
    return {"address": address, "linked_at": now}


async def get_wallet(user_id: str) -> dict:
    link = await repo.get_wallet_link(user_id)
    if link is None:
        return {"address": None, "linked_at": None}
    return {"address": _checksum(link["address"]), "linked_at": link["linked_at"]}


async def unlink(user_id: str) -> bool:
    """Only removes the link here. The vault and its tokens stay the owner's."""
    return await repo.delete_wallet_link(user_id)
