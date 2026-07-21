import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const component = readFileSync(new URL("../components/RiskIntelligence.tsx", import.meta.url), "utf8");

test("risk intelligence separates severity, confidence, completeness and freshness", () => {
  for (const text of ["Severity", "Evidence confidence", "Data completeness", "Source freshness", "Feature contributions", "Evidence drawer", "Historical and replay comparison", "fingerprint"]) assert.match(component, new RegExp(text, "i"));
});

test("risk intelligence exposes degraded states and an analyst-only boundary", () => {
  for (const text of ["Unavailable", "MISSING", "fixture/replay evidence only", "Recommended analyst action", "Autonomous action", "disabled"]) assert.match(component, new RegExp(text, "i"));
  assert.doesNotMatch(component, /<button[^>]*>[^<]*(approve|purchase|release|execute|audit)/i);
});

test("risk severity is not presented as disruption probability", () => {
  assert.match(component, /SEVERITY IS NOT DISRUPTION PROBABILITY/);
  assert.doesNotMatch(component, /\b\d+(?:\.\d+)?% probability\b/i);
});
