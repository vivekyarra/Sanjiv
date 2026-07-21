import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const component = readFileSync(new URL("../components/ResponsePlanner.tsx", import.meta.url), "utf8");

test("response planner exposes all profiles, checker state, provenance and truth labels", () => {
  for (const text of ["LOWEST_COST", "BALANCED", "HIGHEST_RESILIENCE", "MODELED", "assumption-dependent", "Independent", "fingerprint", "Rejected options", "Selected planning profile: BALANCED"]) assert.match(component, new RegExp(text, "i"));
});

test("response planner contains no purchasing or reserve execution control", () => {
  assert.doesNotMatch(component, /<button[^>]*>[^<]*(approve|purchase|book|release)/i);
  assert.match(component, /does not purchase cargo/);
  assert.match(component, /release reserves/);
});
