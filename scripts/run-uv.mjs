import { spawnSync } from "node:child_process";

const isWindows = process.platform === "win32";
const executable = isWindows ? "py" : "uv";
const arguments_ = isWindows ? ["-m", "uv", ...process.argv.slice(2)] : process.argv.slice(2);
const result = spawnSync(executable, arguments_, { stdio: "inherit", shell: false });

if (result.error) throw result.error;
process.exit(result.status ?? 1);
