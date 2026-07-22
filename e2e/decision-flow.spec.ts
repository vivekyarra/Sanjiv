import { expect, test, type Page } from "@playwright/test";

const SCREENSHOTS = "reports/e2e/screenshots";

async function capture(page: Page, name: string) {
  if (process.env.SANJIV_UPDATE_EVIDENCE !== "1") return;
  await page.screenshot({ path: `${SCREENSHOTS}/${name}.png`, fullPage: true });
}

test("Observe -> Detect -> Simulate -> Optimise -> Approve -> Monitor", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Live Maritime Watch", exact: true })).toBeVisible();
  await expect(page.getByText(/REPLAY|FIXTURE/).first()).toBeVisible();
  await expect(page.getByText("PORTWATCH CURRENT", { exact: true })).toBeVisible({ timeout: 30_000 });
  await capture(page, "01-live-maritime-watch");

  await page.goto("/digital-twin");
  await expect(page.getByRole("heading", { name: "Digital Twin", exact: true })).toBeVisible();
  await expect(page.getByText("CONSERVED", { exact: true })).toBeVisible();
  await expect(page.getByText(/ASSUMPTION-DRIVEN REFERENCE TWIN/)).toBeVisible();
  await capture(page, "02-digital-twin");

  await page.goto("/risk-intelligence");
  await expect(page.getByRole("heading", { name: "Risk Intelligence" })).toBeVisible();
  await expect(page.getByText(/not disruption probability/i)).toBeVisible();
  await expect(page.getByRole("region", { name: "Current IMF PortWatch observation" })).toBeVisible({ timeout: 30_000 });
  await capture(page, "03-risk-intelligence");

  await page.goto("/scenario-lab");
  await expect(page.getByText(/Scenario Lab/).first()).toBeVisible();
  await expect(page.getByLabel("Supported scenario text")).toHaveValue(
    "Close the Strait of Hormuz for 14 days.",
  );
  await page.getByRole("button", { name: "Compile and validate" }).click();
  await expect(page.getByRole("heading", { name: "Close the Strait of Hormuz for 14 days" })).toBeVisible();
  await expect(page.getByText(/Scenario fingerprint/)).toBeVisible();
  await page.getByRole("button", { name: "Confirm frozen scenario" }).click();
  await expect(page.getByRole("heading", { name: "Frozen and ready" })).toBeVisible();
  const simulationResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/v1/scenario-runs") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Run deterministic no-action simulation" }).click();
  const simulation = (await (await simulationResponse).json()) as { run_id: string };
  const runId = simulation.run_id;
  await expect(page.getByText(/bounded sensitivity, not a statistical probability/i)).toBeVisible();
  await expect(page.getByText(/Measured simulation runtime/)).toBeVisible();
  await capture(page, "04-scenario-lab");

  await page.goto("/response-planner");
  await page.getByLabel("Completed scenario run ID").fill(runId);
  const procurementResponse = page.waitForResponse(
    (response) => response.url().endsWith(`/api/v1/scenario-runs/${runId}/procurement-plans`) && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate modeled plans" }).click();
  const procurement = (await (await procurementResponse).json()) as {
    plans: Array<{ plan_id: string; profile: string }>;
  };
  const balancedId = procurement.plans.find((item) => item.profile === "BALANCED")?.plan_id;
  expect(balancedId).toBeTruthy();
  await expect(
    page.locator('section[aria-label="Procurement profiles"]').getByRole("heading", { name: "BALANCED" }),
  ).toBeVisible();
  await expect(page.getByText(/independently satisfied/).first()).toBeVisible();
  await capture(page, "05-response-planner");

  await page.goto("/strategic-reserve");
  await page.getByLabel("Completed scenario run ID").fill(runId);
  await page.getByLabel("Checked procurement plan ID").fill(balancedId!);
  await page.getByRole("button", { name: "Generate modeled guidance" }).click();
  await expect(page.getByText(/ASSUMPTION-DEPENDENT OPENING FILL/i)).toBeVisible();
  await expect(
    page.locator('section[aria-label="Reserve policy profiles"]').getByText("PASSED", { exact: true }).first(),
  ).toBeVisible();
  await capture(page, "06-strategic-reserve");

  await page.goto("/evidence-approval");
  await page.getByLabel("Procurement or reserve plan ID").fill(balancedId!);
  await page.getByRole("button", { name: "Run Evidence Audit" }).click();
  await expect(page.getByText(/PASSED.*100\.0% coverage/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Why this plan?" })).toBeVisible();
  const workflow = page.getByRole("heading", { name: /Review workflow/ });
  if ((await workflow.textContent())?.includes("RECOMMENDED")) {
    await page.getByLabel("Configured demo identity and role").selectOption("operator");
    await page.getByRole("button", { name: "Submit for review" }).click();
    await page.getByLabel("Configured demo identity and role").selectOption("reviewer");
    await page.getByRole("button", { name: "Record review" }).click();
    await page.getByLabel("Configured demo identity and role").selectOption("approver");
    await page.getByRole("button", { name: "Approve" }).click();
  }
  await expect(workflow).toContainText("APPROVED");
  await capture(page, "07-evidence-human-approval");

  await page.goto("/historical-replay");
  await page.getByRole("button", { name: "LPG" }).click();
  await page.getByRole("button", { name: "Run deterministic replay" }).click();
  await expect(page.getByRole("heading", { name: "LPG candidate allocations" })).toBeVisible();
  await page.getByLabel("Audited plan ID").fill(balancedId!);
  await page.getByRole("button", { name: "Run sensitivity" }).click();
  await expect(page.getByText(/not calibrated.*probability/i)).toBeVisible();
  await page.getByRole("button", { name: "Compare with replay outcome" }).click();
  await expect(page.getByText(/No order-placement or reserve-execution integration/i)).toBeVisible();
  await page.getByRole("button", { name: "Create audited JSON package" }).click();
  await expect(page.getByText("MACHINE_READABLE_JSON ready")).toBeVisible();
  await capture(page, "08-replay-lpg-monitoring-export");
});
