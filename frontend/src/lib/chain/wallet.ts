// Browser wallet (MetaMask or any EIP-1193 wallet) through ethers.
// Every write here goes from the user's wallet straight to a contract; the
// backend never holds the user's key and is never asked to move funds.
import { BrowserProvider, Contract, type Eip1193Provider, type Signer } from 'ethers'
import { FACTORY_ABI, FEED_ABI, MANDATES_ABI, TASKS_ABI, TOKEN_ABI, VAULT_ABI } from './abi'

declare global {
  interface Window {
    ethereum?: Eip1193Provider & { on?: (event: string, cb: (...args: unknown[]) => void) => void }
  }
}

export class WalletError extends Error {}

const LOCAL_CHAIN = {
  chainId: '0x7a69', // 31337
  chainName: 'Hardhat (local)',
  rpcUrls: ['http://127.0.0.1:8545'],
  nativeCurrency: { name: 'Test ETH', symbol: 'ETH', decimals: 18 },
}

export const hasWallet = () => typeof window !== 'undefined' && !!window.ethereum

export interface Connection {
  provider: BrowserProvider
  signer: Signer
  address: string
}

export async function connectWallet(chainId: number): Promise<Connection> {
  if (!window.ethereum) throw new WalletError('No browser wallet found. Install MetaMask to use the vault.')
  const provider = new BrowserProvider(window.ethereum)
  await provider.send('eth_requestAccounts', [])
  const network = await provider.getNetwork()
  if (Number(network.chainId) !== chainId) await switchChain(chainId)
  const fresh = new BrowserProvider(window.ethereum)
  const signer = await fresh.getSigner()
  return { provider: fresh, signer, address: await signer.getAddress() }
}

async function switchChain(chainId: number) {
  const hex = '0x' + chainId.toString(16)
  try {
    await window.ethereum!.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: hex }] })
  } catch (err: any) {
    if (err?.code === 4902 && chainId === 31337) {
      await window.ethereum!.request({ method: 'wallet_addEthereumChain', params: [LOCAL_CHAIN] })
      return
    }
    throw new WalletError(`Switch your wallet to chain ${chainId} to continue.`)
  }
}

export function contractsFor(signer: Signer, addresses: Record<string, string>) {
  const at = (name: string, abi: string[]) => new Contract(addresses[name], abi, signer)
  return {
    inr: at('tINR', TOKEN_ABI),
    funds: {
      tEquityFund: at('tEquityFund', TOKEN_ABI),
      tDebtFund: at('tDebtFund', TOKEN_ABI),
      tGoldFund: at('tGoldFund', TOKEN_ABI),
    },
    factory: at('VaultFactory', FACTORY_ABI),
    mandates: at('MandateManager', MANDATES_ABI),
    tasks: at('AITaskManager', TASKS_ABI),
    feed: at('MockPriceFeed', FEED_ABI),
    vault: (address: string) => new Contract(address, VAULT_ABI, signer),
  }
}

export type Contracts = ReturnType<typeof contractsFor>

/** A short reason for a failed wallet action, without the raw RPC dump. */
export function walletErrorMessage(err: unknown): string {
  const e = err as any
  if (e?.code === 'ACTION_REJECTED' || e?.code === 4001) return 'You cancelled this in your wallet.'
  const reason = e?.reason || e?.shortMessage || e?.message
  return typeof reason === 'string' ? reason.slice(0, 200) : 'The transaction failed.'
}
