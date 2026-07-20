import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";

test("shell uses final product branding", () => {
  const page = fs.readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(page, /Sanjiv/);
  assert.match(page, /Keep India’s energy moving\./);
  const forbidden = ["JA" + "NUS", "Sanjiv" + "GPT", "Sanjiv" + " AI"];
  for (const name of forbidden) assert.doesNotMatch(page, new RegExp(name));
});
