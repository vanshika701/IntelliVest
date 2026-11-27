import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { blockchainApi, type ChainTask } from '../../api/blockchain'
import { Sidebar } from '../layout/Sidebar'
import { LayoutProvider } from '../../LayoutContext'
import { AuthProvider } from '../../AuthContext'
import { WalletCard } from './WalletCard'
import { AiTradesCard } from './AiTradesCard'
import type { VaultState } from './useVaultState'

vi.mock('../../api/blockchain', () => ({
  blockchainApi: {
    status: vi.fn(),
    challenge: vi.fn(),
    verify: vi.fn(),
    unlink: vi.fn(),
    createTask: vi.fn(),
  },
}))

const api = vi.mocked(blockchainApi)
const ADDRESS = '0x1111111111111111111111111111111111111111'
const tx = (fn = vi.fn()) => vi.fn(async (...args: unknown[]) => (fn(...args), { wait: async () => ({}) }))

function renderSidebar() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LayoutProvider>
          <Sidebar />
        </LayoutProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.ethereum = {} as any
  // jsdom has no matchMedia; the layout uses it to open the sidebar on wide screens.
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }) as any
})

describe('feature flag (B17)', () => {
  it('shows no vault link while blockchain is off', async () => {
    api.status.mockResolvedValue({ enabled: false, privacy_notice: '' })
    renderSidebar()
    await waitFor(() => expect(api.status).toHaveBeenCalled())
    expect(screen.queryByText('AI vault')).not.toBeInTheDocument()
    expect(screen.getByText('Portfolio plan')).toBeInTheDocument()
  })

  it('shows the vault link when it is on', async () => {
    api.status.mockResolvedValue({ enabled: true, privacy_notice: '' })
    renderSidebar()
    expect(await screen.findByText('AI vault')).toBeInTheDocument()
  })
})

describe('WalletCard', () => {
  it('links the wallet by signing the one-time challenge', async () => {
    api.challenge.mockResolvedValue({ message: 'sign me', expires_at: '' })
    api.verify.mockResolvedValue({ address: ADDRESS })
    const signMessage = vi.fn().mockResolvedValue('0xsig')
    const onLinkChange = vi.fn()
    render(
      <WalletCard connection={{ address: ADDRESS, signer: { signMessage } } as any} link={{ address: null }}
        onConnect={async () => {}} onLinkChange={onLinkChange} />,
    )
    await userEvent.click(screen.getByRole('button', { name: /link this wallet/i }))
    await waitFor(() => expect(onLinkChange).toHaveBeenCalled())
    expect(signMessage).toHaveBeenCalledWith('sign me')
    expect(api.verify).toHaveBeenCalledWith(ADDRESS, '0xsig')
  })

  it('warns when the connected wallet is not the linked one', () => {
    render(
      <WalletCard connection={{ address: ADDRESS, signer: {} } as any}
        link={{ address: '0x2222222222222222222222222222222222222222' }} onConnect={async () => {}} onLinkChange={() => {}} />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/not the one linked/)
  })

  it('says when there is no browser wallet', () => {
    window.ethereum = undefined
    render(<WalletCard connection={null} link={{ address: null }} onConnect={async () => {}} onLinkChange={() => {}} />)
    expect(screen.getByText(/Install MetaMask/)).toBeInTheDocument()
  })
})

const state: VaultState = {
  vault: '0x3333333333333333333333333333333333333333',
  cash: 0n, wallet: 0n,
  units: { tEquityFund: 0n, tDebtFund: 0n, tGoldFund: 0n },
  prices: {} as VaultState['prices'],
  aiPaused: false, mandateActive: true, mandate: null, allowedFunds: [], sip: null,
}

const task = (over: Partial<ChainTask>): ChainTask => ({
  id: 't1', fund: 'tEquityFund', ticker: 'RELIANCE', state: 'pending_user', task_id: '0xabc', vault: state.vault,
  outcome: 'PENDING_USER', reason: 'NONE', amount_out: null, last_error: null, mock_advisor: true,
  created_at: '', updated_at: '',
  evidence: [{ step: 'stock_prediction', status: 'NO_DATA', score: 0, inputs: { reason: 'no stored prediction' }, outputs: {}, tx_hash: '0xdef' }],
  proposal: {
    model: 'intellivest/mock-advisor', model_version: '1', side: 'BUY', amount: '100000000', minimum_received: '990000',
    confidence: 9000, deadline: 0, explanation: { text: 'Mock rule', contributions: {} },
  },
  ...over,
})

function contracts() {
  const approve = vi.fn()
  const setAiPaused = vi.fn()
  return {
    approve, setAiPaused,
    value: { tasks: { approve: tx(approve), decline: tx() }, vault: () => ({ setAiPaused: tx(setAiPaused) }) } as any,
  }
}

describe('AiTradesCard (B15)', () => {
  it('approves a pending trade from the wallet', async () => {
    const c = contracts()
    const onChange = vi.fn()
    render(<AiTradesCard contracts={c.value} state={state} tasks={[task({})]} onChange={onChange} />)
    expect(screen.getByText('Needs your approval')).toBeInTheDocument()
    expect(screen.getByText(/mock advisor/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(onChange).toHaveBeenCalled())
    expect(c.approve).toHaveBeenCalledWith('0xabc')
  })

  it('shows evidence and the reason for a rejection', async () => {
    const c = contracts()
    render(<AiTradesCard contracts={c.value} state={state}
      tasks={[task({ state: 'rejected', outcome: 'REJECTED', reason: 'OVER_TRADE_CAP' })]} onChange={() => {}} />)
    expect(screen.getByText(/above your per-trade cap/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Evidence' }))
    expect(screen.getByText(/Stock prediction: NO_DATA/)).toBeInTheDocument()
    expect(screen.getByText(/intellivest\/mock-advisor v1 \(mock\)/)).toBeInTheDocument()
  })

  it('revoke AI pauses the vault from the wallet', async () => {
    const c = contracts()
    render(<AiTradesCard contracts={c.value} state={state} tasks={[]} onChange={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Revoke AI' }))
    await waitFor(() => expect(c.setAiPaused).toHaveBeenCalledWith(true))
  })

  it('cannot ask the AI without an active mandate', () => {
    const c = contracts()
    render(<AiTradesCard contracts={c.value} state={{ ...state, mandateActive: false }} tasks={[]} onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'Ask the AI' })).toBeDisabled()
  })
})
