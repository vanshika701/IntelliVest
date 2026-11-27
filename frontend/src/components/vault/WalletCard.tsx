import { Link2, Wallet } from 'lucide-react'
import { blockchainApi, type WalletLink } from '../../api/blockchain'
import { Button } from '../ui/Button'
import { hasWallet, type Connection } from '../../lib/chain/wallet'
import { ActionMessage, Card, muted, shortAddress, useAction } from './shared'

/** Connect a browser wallet and prove it is yours by signing a one-time
 * message. Signing is free and moves nothing. */
export function WalletCard({ connection, link, onConnect, onLinkChange }: {
  connection: Connection | null
  link: WalletLink | undefined
  onConnect: () => Promise<void>
  onLinkChange: () => void
}) {
  const { busy, error, done, run } = useAction()
  const linked = link?.address ?? null
  const mismatch = connection && linked && connection.address.toLowerCase() !== linked.toLowerCase()

  async function linkWallet() {
    if (!connection) return
    const ok = await run('link', async () => {
      const { message } = await blockchainApi.challenge(connection.address)
      const signature = await connection.signer.signMessage(message)
      await blockchainApi.verify(connection.address, signature)
    }, 'Wallet linked.')
    if (ok) onLinkChange()
  }

  async function unlink() {
    const ok = await run('unlink', () => blockchainApi.unlink(), 'Wallet unlinked. Your vault and tokens are untouched.')
    if (ok) onLinkChange()
  }

  return (
    <Card id="wallet-heading" icon={Wallet} title="Wallet">
      {!hasWallet() ? (
        <p className={muted}>No browser wallet found. Install MetaMask, then reload this page.</p>
      ) : !connection ? (
        <Button onClick={() => run('connect', onConnect)} disabled={busy !== null}>
          {busy === 'connect' ? 'Connecting…' : 'Connect wallet'}
        </Button>
      ) : (
        <p className="text-sm text-[var(--color-text-primary)]">
          Connected: <span className="font-mono">{shortAddress(connection.address)}</span>
        </p>
      )}

      {linked ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-[var(--color-text-secondary)]">
            Linked to your account: <span className="font-mono">{shortAddress(linked)}</span>
          </p>
          <Button variant="outline" size="sm" onClick={unlink} disabled={busy !== null}>Unlink</Button>
        </div>
      ) : connection ? (
        <Button variant="outline" onClick={linkWallet} disabled={busy !== null}>
          <Link2 className="mr-2 h-4 w-4" aria-hidden="true" />
          {busy === 'link' ? 'Check your wallet…' : 'Link this wallet'}
        </Button>
      ) : null}
      {mismatch && (
        <p role="alert" className="text-sm text-[var(--color-losses)]">
          The connected wallet is not the one linked to your account. Switch accounts in your wallet.
        </p>
      )}
      <ActionMessage error={error} done={done} />
    </Card>
  )
}
