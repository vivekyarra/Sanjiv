import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const mode = process.argv[2];
if (!["--write", "--check"].includes(mode)) {
  throw new Error("usage: node scripts/contracts.mjs --write|--check");
}

const root = resolve(import.meta.dirname, "..");
const openapiTarget = join(root, "packages", "contracts", "openapi.json");
const typesTarget = join(root, "packages", "contracts", "src", "generated.ts");
const temp = mkdtempSync(join(tmpdir(), "sanjiv-contracts-"));
const openapiTemp = join(temp, "openapi.json");
const typesTemp = join(temp, "generated.ts");
const openapiTypescript = join(root, "node_modules", "openapi-typescript", "bin", "cli.js");
const uvCommand = process.platform === "win32" ? "py" : "uv";
const uvPrefix = process.platform === "win32" ? ["-m", "uv"] : [];

try {
  execFileSync(
    uvCommand,
    [...uvPrefix, "run", "python", "scripts/export_openapi.py", "--output", openapiTemp],
    { cwd: root, stdio: "inherit" },
  );
  execFileSync(process.execPath, [openapiTypescript, openapiTemp, "--output", typesTemp], {
    cwd: root,
    stdio: "inherit",
  });
  if (mode === "--write") {
    const { copyFileSync } = await import("node:fs");
    copyFileSync(openapiTemp, openapiTarget);
    copyFileSync(typesTemp, typesTarget);
  } else {
    const expectedOpenapi = readFileSync(openapiTarget, "utf8").replaceAll("\r\n", "\n");
    const actualOpenapi = readFileSync(openapiTemp, "utf8").replaceAll("\r\n", "\n");
    const expectedTypes = readFileSync(typesTarget, "utf8").replaceAll("\r\n", "\n");
    const actualTypes = readFileSync(typesTemp, "utf8").replaceAll("\r\n", "\n");
    if (expectedOpenapi !== actualOpenapi || expectedTypes !== actualTypes) {
      throw new Error("generated contracts are stale; run npm run contracts:generate");
    }
  }
} finally {
  rmSync(temp, { recursive: true, force: true });
}
