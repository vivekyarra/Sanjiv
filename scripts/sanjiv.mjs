import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";

function run(command, args, options = {}) {
  let executable = isWindows && command === "npm" ? "npm.cmd" : command;
  let executableArgs = args;
  if (isWindows && command === "uv") {
    executable = "py";
    executableArgs = ["-m", "uv", ...args];
  }
  const result = spawnSync(executable, executableArgs, {
    cwd: root,
    stdio: "inherit",
    env: process.env,
    shell: false,
    ...options,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

function compose(args) {
  run("docker", ["compose", ...args]);
}

const commands = {
  install() {
    run("npm", ["ci"]);
    run("uv", ["sync", "--all-groups", "--locked"]);
  },
  services() {
    compose(["up", "-d", "postgres", "redis", "minio", "--wait"]);
  },
  migrate() {
    run("uv", ["run", "alembic", "upgrade", "head"]);
  },
  seed() {
    run("uv", ["run", "python", "scripts/seed_demo.py"]);
  },
  start() {
    commands.services();
    commands.migrate();
    compose(["--profile", "app", "up", "-d", "--build", "--wait"]);
    commands.seed();
    commands.preflight();
  },
  dev() {
    commands.services();
    commands.migrate();
    run("npm", ["run", "dev"]);
  },
  workers() {
    compose(["--profile", "app", "up", "-d", "ingestion-worker", "refresh-worker", "compute-worker"]);
  },
  verify() {
    commands.services();
    commands.migrate();
    run("npm", ["run", "contracts:check"]);
    run("npm", ["run", "lint"]);
    run("npm", ["run", "typecheck"]);
    run("npm", ["test"]);
    run("npm", ["run", "build"]);
  },
  full() {
    commands.start();
    commands.verify();
    run("uv", ["run", "alembic", "downgrade", "-1"]);
    run("uv", ["run", "alembic", "upgrade", "head"]);
    run("npm", ["run", "test:e2e", "--", "--reporter=line"]);
    run("uv", ["run", "python", "scripts/benchmark_phase9.py"]);
    run("uv", ["run", "python", "scripts/backup_restore.py"]);
    run("uv", ["run", "python", "scripts/reliability_drill.py"]);
    run("uv", ["run", "python", "scripts/security_scan.py", "--images"]);
    commands.offline();
    run("docker", ["compose", "config", "--quiet"]);
    run("git", ["diff", "--check"]);
  },
  preflight() {
    run("uv", ["run", "python", "scripts/demo_preflight.py"]);
  },
  demo() {
    commands.start();
    console.log("Sanjiv demo ready at http://localhost:3000 — SYNTHETIC_FIXTURE / REPLAY, not live.");
  },
  offline() {
    compose(["--profile", "offline", "up", "-d", "--no-build", "--wait"]);
    commands.preflight();
  },
  stop() {
    compose(["--profile", "app", "--profile", "offline", "down"]);
  },
  cleanup() {
    compose(["--profile", "app", "--profile", "offline", "down", "-v", "--remove-orphans"]);
  },
};

const command = process.argv[2];
if (!command || !(command in commands)) {
  console.error(`Usage: node scripts/sanjiv.mjs <${Object.keys(commands).join("|")}>`);
  process.exit(2);
}
commands[command]();
