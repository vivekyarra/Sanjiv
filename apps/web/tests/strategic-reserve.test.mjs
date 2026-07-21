import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const component = readFileSync(new URL("../components/StrategicReserve.tsx", import.meta.url), "utf8");

test("strategic reserve shows policy, site truth, coordination, solver and provenance", () => {
  for (const text of ["CONSERVATIVE", "BALANCED", "AGGRESSIVE_CONTINUITY", "NO_RESERVE_USE", "three reserve sites", "capacity", "opening-fill truth", "Procurement coordination", "Solver", "Checker", "Evidence", "assumptions", "fingerprints"]) assert.match(component, new RegExp(text, "i"));
});

test("strategic reserve states recommendation boundary and has no execution control", () => {
  assert.match(component, /Sanjiv recommends guidance only/);
  assert.match(component, /does not release reserves/);
  assert.doesNotMatch(component, /<button[^>]*>[^<]*(approve|release|purchase|execute)/i);
});
