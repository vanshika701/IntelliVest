// Only the contract functions the vault screens use, in ethers' readable ABI
// form. Source of truth: blockchain/contracts (Types.sol for the structs).

const MANDATE =
  'tuple(uint64 start, uint64 end, uint128 perTradeCap, uint128 dailyCap, uint128 monthlyCap, ' +
  'uint128 userSignAbove, uint16 maxEquityBps, uint16 maxSlippageBps, uint16 maxLossBps, ' +
  'uint16 maxTradesPerDay, uint16 confidenceThreshold, bool requireSentiment, bool requireStock, ' +
  'bool askUserOnNoData)'

export const TOKEN_ABI = [
  'function balanceOf(address) view returns (uint256)',
  'function allowance(address owner, address spender) view returns (uint256)',
  'function approve(address spender, uint256 amount) returns (bool)',
  'function faucet(uint256 amount)',
  'function FAUCET_LIMIT() view returns (uint256)',
]

export const FACTORY_ABI = [
  'function vaultOf(address owner) view returns (address)',
  'function createVault() returns (address)',
]

export const VAULT_ABI = [
  'function owner() view returns (address)',
  'function aiPaused() view returns (bool)',
  'function deposit(uint256 amount)',
  'function withdraw(address token, uint256 amount)',
  'function setAiPaused(bool paused)',
  'function setSip(address fund, uint128 amount, uint8 dayOfMonth, uint16 maxSlippageBps, uint64 end)',
  'function cancelSip()',
  'function sip() view returns (address fund, uint128 amount, uint16 maxSlippageBps, uint8 dayOfMonth, uint64 nextRun, uint64 end)',
  'function portfolio() view returns (uint256 total, uint256 equity, bool fresh)',
]

export const MANDATES_ABI = [
  `function setMandate(address vault, ${MANDATE} m, address[] funds, bytes32[] models)`,
  `function mandateOf(address vault) view returns (${MANDATE})`,
  'function active(address vault) view returns (bool)',
  'function revokeMandate(address vault)',
  'function fundAllowed(address vault, address fund) view returns (bool)',
]

export const TASKS_ABI = [
  'function approve(bytes32 taskId)',
  'function decline(bytes32 taskId)',
]

export const FEED_ABI = ['function price(address fund) view returns (uint256 value, uint256 updatedAt)']
