"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navigation = [
  { href: "/", label: "Maritime", icon: "radar" },
  { href: "/digital-twin", label: "Network", icon: "network" },
  { href: "/risk-intelligence", label: "Risk", icon: "risk" },
  { href: "/scenario-lab", label: "Scenarios", icon: "spark" },
  { href: "/response-planner", label: "Response", icon: "route" },
  { href: "/strategic-reserve", label: "Reserve", icon: "reserve" },
  { href: "/evidence-approval", label: "Approval", icon: "check" },
  { href: "/historical-replay", label: "Replay", icon: "replay" },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="app-frame">
      <aside className="app-rail" aria-label="Sanjiv navigation">
        <Link className="rail-brand" href="/" aria-label="Sanjiv home">
          <span className="rail-mark" aria-hidden="true">S</span>
          <span><strong>Sanjiv</strong><small>Command Center</small></span>
        </Link>
        <nav className="rail-nav" aria-label="Command modules">
          {navigation.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                className={active ? "rail-link active" : "rail-link"}
                href={item.href}
                aria-current={active ? "page" : undefined}
                title={item.label}
              >
                <AppIcon name={item.icon} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="rail-footer">
          <span className="pulse-dot" aria-hidden="true" />
          <span><strong>Decision support</strong><small>Human in control</small></span>
        </div>
      </aside>
      <div className="app-workspace">{children}</div>
    </div>
  );
}

function AppIcon({ name }: { name: (typeof navigation)[number]["icon"] }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const paths = {
    radar: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 12l5-5M12 4v2M20 12h-2" /></>,
    network: <><rect x="3" y="4" width="6" height="5" rx="1.5" /><rect x="15" y="15" width="6" height="5" rx="1.5" /><rect x="3" y="15" width="6" height="5" rx="1.5" /><path d="M9 6.5h4a4 4 0 0 1 4 4V15M9 17.5h6M6 9v6" /></>,
    risk: <><path d="M12 3l8 4v5c0 4.6-3.3 7.6-8 9-4.7-1.4-8-4.4-8-9V7l8-4z" /><path d="M12 8v5M12 16.5v.1" /></>,
    spark: <><path d="M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3z" /><path d="M18 16l.7 2.3L21 19l-2.3.7L18 22l-.7-2.3L15 19l2.3-.7L18 16z" /></>,
    route: <><circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="6" r="2.5" /><path d="M8.5 18h2a3 3 0 0 0 3-3v-6a3 3 0 0 1 3-3h-1" /></>,
    reserve: <><path d="M4 8h16M6 8v11M10 8v11M14 8v11M18 8v11M3 20h18M12 3l9 4H3l9-4z" /></>,
    check: <><circle cx="12" cy="12" r="9" /><path d="M8 12l2.7 2.7L16.5 9" /></>,
    replay: <><path d="M4 11a8 8 0 1 1 2.3 6M4 11V5M4 11h6" /><path d="M11 8v5l3 2" /></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true" {...common}>{paths[name]}</svg>;
}
