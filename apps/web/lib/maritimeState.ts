export type OperatingMode = "LIVE" | "DEGRADED" | "REPLAY";
export type SocketState = "CONNECTING" | "CONNECTED" | "DISCONNECTED" | "ERROR";

export function modePresentation(mode: OperatingMode) {
  if (mode === "LIVE") return { label: "LIVE", tone: "live", warning: null } as const;
  if (mode === "REPLAY") {
    return {
      label: "REPLAY — NOT LIVE DATA",
      tone: "replay",
      warning: "Synthetic or recorded replay is active. Original source timestamps are preserved.",
    } as const;
  }
  return {
    label: "DEGRADED",
    tone: "degraded",
    warning: "The live maritime source is unavailable or recovering.",
  } as const;
}

export function connectionLabel(state: SocketState) {
  return {
    CONNECTING: "Connecting",
    CONNECTED: "Connected",
    DISCONNECTED: "Disconnected — reconnecting",
    ERROR: "Connection error — retrying",
  }[state];
}

export function hasStaleVessels(statuses: string[]) {
  return statuses.some((status) => status === "STALE" || status === "UNAVAILABLE");
}

export function reconnectDelay(attempt: number) {
  return Math.min(1000 * 2 ** Math.max(0, attempt), 30000);
}
