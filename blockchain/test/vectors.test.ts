import { expect } from "chai";
import { readFileSync } from "node:fs";
import { ethers, TYPES, deploy, networkHelpers } from "./helpers.js";

// The same file is checked by backend/tests/test_blockchain_hashing.py.
const vectors = JSON.parse(readFileSync(new URL("../test-vectors/signing.json", import.meta.url), "utf8"));

describe("Shared hash vectors", () => {
  for (const name of ["Evidence", "Proposal"] as const) {
    it(`${name} matches the contract and ethers`, async () => {
      const c = await networkHelpers.loadFixture(deploy);
      const v = vectors[name];
      const onChain = name === "Evidence" ? await c.manager.hashEvidence(v.message) : await c.manager.hashProposal(v.message);
      expect(onChain).to.equal(v.structHash);
      expect(ethers.TypedDataEncoder.hash(vectors.domain, { [name]: TYPES[name] }, v.message)).to.equal(v.digest);
    });
  }
});
