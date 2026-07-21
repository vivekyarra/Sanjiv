import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const panel = readFileSync(new URL("../components/GovernancePanel.tsx", import.meta.url), "utf8");
const page = readFileSync(new URL("../app/evidence-approval/page.tsx", import.meta.url), "utf8");

test("Evidence and Approval uses real audit, explanation, assumption, and lifecycle APIs", () => {
  for (const endpoint of ["/audit", "/explanation", "/governance", "/assumptions", '"reviews"', '"approvals"', '"rejections"']) {
    assert.match(panel, new RegExp(endpoint));
  }
  assert.match(panel, /KPI evidence drawer/);
  assert.match(panel, /Assumption drawer/);
  assert.match(panel, /Recomputation status/);
  assert.match(panel, /Recommendation blocked/);
  assert.match(page, /SERVER-ENFORCED/);
});

test("approval UI preserves human authority and contains no execution control", () => {
  assert.match(panel, /does not place orders, charter vessels, release reserves/);
  assert.match(panel, /Submit for review/);
  assert.match(panel, />Approve</);
  assert.match(panel, />Reject</);
  assert.doesNotMatch(panel, /Book tanker|Place order|Execute release/);
});

test("every decision module has permanent Evidence and Approval navigation", () => {
  for (const relative of [
    "../components/MaritimeWatch.tsx",
    "../components/DigitalTwin.tsx",
    "../components/ScenarioLab.tsx",
    "../components/ResponsePlanner.tsx",
    "../components/StrategicReserve.tsx",
    "../components/RiskIntelligence.tsx",
  ]) {
    const source = readFileSync(new URL(relative, import.meta.url), "utf8");
    assert.match(source, /href="\/evidence-approval"/);
  }
});
