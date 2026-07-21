import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

test("measure map FPS and interaction latency without prewritten values", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/Live Maritime Watch/)).toBeVisible();
  const frames = await page.evaluate(async () => {
    const values: number[] = [];
    let previous = performance.now();
    for (let index = 0; index < 120; index += 1) {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      const now = performance.now();
      values.push(now - previous);
      previous = now;
    }
    return values;
  });
  const interactionStarted = performance.now();
  await page.getByRole("link", { name: "Digital Twin" }).click();
  await expect(page.getByRole("heading", { name: "Sanjiv" })).toBeVisible();
  const interactionLatency = performance.now() - interactionStarted;
  const sorted = [...frames].sort((left, right) => left - right);
  const total = frames.reduce((sum, value) => sum + value, 0);
  const fps = 1000 / (total / frames.length);
  const report = {
    schema_version: "1.0",
    timestamp: new Date().toISOString(),
    viewport: await page.viewportSize(),
    sample_frames: frames.length,
    map_fps: Number(fps.toFixed(3)),
    frame_time_ms: {
      minimum: Number(sorted[0].toFixed(3)),
      median: Number(sorted[Math.floor(sorted.length / 2)].toFixed(3)),
      p95: Number(sorted[Math.floor(sorted.length * 0.95)].toFixed(3)),
      maximum: Number(sorted.at(-1)!.toFixed(3)),
    },
    interaction_latency_ms: Number(interactionLatency.toFixed(3)),
    classification: "MEASURED_LOCAL_BROWSER_REPLAY",
    notice: "Actual browser measurements, not an SLA or target claim.",
  };
  const target = path.resolve("reports/performance/browser-benchmark.json");
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, `${JSON.stringify(report, null, 2)}\n`, "utf8");
});
