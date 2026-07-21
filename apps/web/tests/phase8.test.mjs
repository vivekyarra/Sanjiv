import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const component = await readFile(new URL("../components/AdvancedDecisionCenter.tsx", import.meta.url), "utf8");
const page = await readFile(new URL("../app/historical-replay/page.tsx", import.meta.url), "utf8");

test("historical replay UI uses real replay, LPG, sensitivity, export and monitoring APIs", () => {
  for (const endpoint of [
    "/api/v1/replay-catalogue",
    "/api/v1/lpg/network",
    "/api/v1/replay-cases/",
    "/sensitivity-runs",
    "/exports",
    "/monitoring",
    "/comments",
  ]) assert.match(component, new RegExp(endpoint.replaceAll("/", "\\/")));
  assert.match(page, /AdvancedDecisionCenter/);
});

test("advanced UI keeps fixture truth, audit blocking and human execution boundaries visible", () => {
  assert.match(component, /SYNTHETIC FIXTURE · NOT LIVE/);
  assert.match(component, /not probability/i);
  assert.match(component, /blocked from usable export/i);
  assert.match(component, /No order-placement or reserve-execution integration/);
  assert.match(component, /RESERVE · NOT APPLICABLE/);
  assert.match(component, /loading/i);
  assert.match(component, /Explicit degraded state/);
  assert.match(component, /No replay selected/);
});

test("advanced UI provides accessible commodity and replay controls", () => {
  assert.match(component, /aria-label="Commodity selector"/);
  assert.match(component, /aria-label="No-action and recommendation timeline"/);
  assert.match(component, /Crude oil/);
  assert.match(component, />LPG</);
  assert.match(component, /Run deterministic replay/);
});

test("every decision screen links to historical replay", async () => {
  const files = [
    "MaritimeWatch.tsx",
    "DigitalTwin.tsx",
    "ScenarioLab.tsx",
    "ResponsePlanner.tsx",
    "StrategicReserve.tsx",
    "RiskIntelligence.tsx",
  ];
  for (const file of files) {
    const source = await readFile(new URL(`../components/${file}`, import.meta.url), "utf8");
    assert.match(source, /href="\/historical-replay"/, file);
  }
});
