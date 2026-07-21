import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(new URL("../components/DigitalTwin.tsx", import.meta.url), "utf8");
const fixture = JSON.parse(readFileSync(new URL("../../../data/fixtures/twin/india-energy-network-v1.json", import.meta.url), "utf8"));

test("digital twin UI exposes snapshot, truth, evidence, assumptions, and mass balance", () => {
  for (const phrase of ["Snapshot version", "Mass balance", "Input source", "Assumptions", "Refinery compatibility", "NOT LIVE OPERATIONAL DATA"]) {
    assert.match(component, new RegExp(phrase));
  }
});

test("digital twin fixture is offline and explicitly classified", () => {
  assert.equal(fixture.records.length, 4);
  assert.ok(fixture.records.every((record) => record.mode !== "LIVE"));
  assert.ok(fixture.records.filter((record) => record.mode === "FIXTURE").every((record) => record.truth_class === "ASSUMPTION"));
});
