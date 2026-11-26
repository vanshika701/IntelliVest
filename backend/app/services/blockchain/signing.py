"""Signs evidence and proposals with one role's key (Phase 10, B10).

Each role (sentiment, stock, advisor) has its own key, so one stolen key
can't sign every step. A signature shows who submitted a result, not that
the model ran or is right.
"""

from dataclasses import dataclass

from eth_account.signers.local import LocalAccount

from app.services.blockchain import hashing
from app.services.blockchain.formats import Evidence, Proposal


@dataclass(frozen=True)
class Signed:
    message: Evidence | Proposal
    signature: bytes
    signer: str


class RoleSigner:
    def __init__(self, account: LocalAccount, chain_id: int, task_manager: str) -> None:
        self._account = account
        self._domain = hashing.domain(chain_id, task_manager)

    @property
    def address(self) -> str:
        return self._account.address

    def __repr__(self) -> str:  # never show the key
        return f"RoleSigner({self.address})"

    def sign_evidence(self, evidence: Evidence) -> Signed:
        return self._sign("Evidence", evidence)

    def sign_proposal(self, proposal: Proposal) -> Signed:
        return self._sign("Proposal", proposal)

    def _sign(self, name: str, message: Evidence | Proposal) -> Signed:
        signable = hashing.typed_message(name, self._domain, message.message())
        signature = bytes(self._account.sign_message(signable).signature)
        return Signed(message, signature, self.address)
