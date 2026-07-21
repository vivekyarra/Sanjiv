import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(new URL("../components/ScenarioLab.tsx", import.meta.url), "utf8");

test("Scenario Lab exposes offline compiler, structured fallback, and confirmation", () => {
  for (const phrase of [
    "Natural-language pattern",
    "Structured fallback",
    "Optional provider unavailable",
    "Resolved assets",
    "Defaults requiring confirmation",
    "Assumptions requiring confirmation",
    "Confirm frozen scenario",
    "SERVER AUDITED",
  ]) {
    assert.match(component, new RegExp(phrase));
  }
});

test("Scenario Lab exposes truthful simulation states and no-action output", () => {
  for (const phrase of [
    "No scenario candidate yet",
    "STALE SNAPSHOT",
    "Simulation progress",
    "CANCELLED",
    "SIMULATION FAILED",
    "Baseline versus no-action",
    "Disruption timeline",
    "Affected routes and flows",
    "Refinery throughput impact",
    "UNKNOWN",
    "ASSUMPTION-DEPENDENT INVENTORY",
    "Deterministic uncertainty range",
    "Measured simulation runtime",
  ]) {
    assert.match(component, new RegExp(phrase));
  }
});

test("Phase 3 UI does not display a procurement recommendation", () => {
  assert.doesNotMatch(component, /recommended procurement/i);
  assert.match(component, /NO PROCUREMENT ACTIONS/);
  assert.match(component, /Future response planning/);
});
