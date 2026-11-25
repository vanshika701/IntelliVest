// Local demo deployment: npm run node, then (second terminal) npm run deploy:local
import { mkdirSync, writeFileSync } from "node:fs";
import { network } from "hardhat";

const { ethers } = await network.getOrCreate();
const chainId = Number((await ethers.provider.getNetwork()).chainId);
if (chainId !== 31337) throw new Error("This script is for the local chain only");

const [deployer] = await ethers.getSigners();
const add: Record<string, string> = {};
async function make(name: string, args: any[] = [], label = name) {
  const contract: any = await ethers.deployContract(name, args);
  await contract.waitForDeployment();
  add[label] = await contract.getAddress();
  return contract;
}

const inr = await make("TestToken", ["Test INR", "tINR", true], "tINR");
const funds = [
  { label: "tEquityFund", token: await make("TestToken", ["Test Equity Fund", "tEquityFund", false], "tEquityFund"), equity: true },
  { label: "tDebtFund", token: await make("TestToken", ["Test Debt Fund", "tDebtFund", false], "tDebtFund"), equity: false },
  { label: "tGoldFund", token: await make("TestToken", ["Test Gold Fund", "tGoldFund", false], "tGoldFund"), equity: false },
];
const feed = await make("MockPriceFeed");
const market = await make("MockFundMarket", [add.tINR, add.MockPriceFeed]);
await (await inr.setMinter(add.MockFundMarket, true)).wait();
for (const { label, token, equity } of funds) {
  await (await token.setMinter(add.MockFundMarket, true)).wait();
  await (await market.addFund(add[label], equity)).wait();
  await (await feed.setPrice(add[label], 100_000_000n)).wait();
}
await make("ModelRegistry");
await make("MandateManager");
await make("AITaskManager", [add.ModelRegistry, add.MandateManager]);
await make("VaultFactory", [add.AITaskManager, add.MandateManager, add.MockFundMarket]);

mkdirSync("deployments", { recursive: true });
writeFileSync("deployments/local.json", JSON.stringify({ chainId, deployer: deployer.address, contracts: add }, null, 2) + "\n");
console.log(add);
