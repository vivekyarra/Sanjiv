import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";

test("shell uses final product branding", () => {
  const page = fs.readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  const watch = fs.readFileSync(new URL("../components/MaritimeWatch.tsx", import.meta.url), "utf8");
  const renderedShell = `${page}\n${watch}`;
  assert.match(renderedShell, /Sanjiv/);
  assert.match(renderedShell, /Keep India’s energy moving\./);
  assert.match(renderedShell, /REPLAY — NOT LIVE DATA/);
  const forbidden = ["JA" + "NUS", "Sanjiv" + "GPT", "Sanjiv" + " AI"];
  for (const name of forbidden) assert.doesNotMatch(renderedShell, new RegExp(name));
});
