import assert from "node:assert/strict";
import test from "node:test";

import {
  connectionLabel,
  hasStaleVessels,
  modePresentation,
  reconnectDelay,
} from "../lib/maritimeState.ts";

test("LIVE and REPLAY modes cannot be visually conflated", () => {
  assert.equal(modePresentation("LIVE").label, "LIVE");
  assert.match(modePresentation("REPLAY").label, /NOT LIVE DATA/);
  assert.match(modePresentation("REPLAY").warning ?? "", /replay/i);
});

test("stale and disconnected states remain explicit", () => {
  assert.equal(hasStaleVessels(["LIVE", "STALE"]), true);
  assert.equal(hasStaleVessels(["LIVE", "RECENT"]), false);
  assert.match(connectionLabel("DISCONNECTED"), /reconnecting/i);
});

test("reconnect backoff is bounded", () => {
  assert.equal(reconnectDelay(0), 1000);
  assert.equal(reconnectDelay(20), 30000);
});
