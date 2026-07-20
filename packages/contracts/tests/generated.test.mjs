import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";

test("generated API contracts exist", () => {
  const generated = fs.readFileSync(new URL("../src/generated.ts", import.meta.url), "utf8");
  assert.match(generated, /MetricEnvelope/);
  assert.match(generated, /EvidenceRecord/);
});
