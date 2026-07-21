import { GovernancePanel } from "../../components/GovernancePanel";
import Link from "next/link";

export default function EvidenceApprovalPage() {
  return <main className="command-shell response-planner"><header className="command-header"><div><p className="eyebrow">India&apos;s Energy Resilience Command Center</p><h1>Evidence &amp; Approval</h1><p>Traceable decision metrics, deterministic explanations, and immutable human authority.</p></div><span className="mode-badge">SERVER-ENFORCED · NO AUTONOMOUS EXECUTION</span></header><nav className="product-nav" aria-label="Product modules"><Link href="/">Live Maritime Watch</Link><Link href="/digital-twin">Digital Twin</Link><Link href="/scenario-lab">Scenario Lab</Link><Link href="/response-planner">Response Planner</Link><Link href="/strategic-reserve">Strategic Reserve</Link><Link href="/risk-intelligence">Risk Intelligence</Link><Link className="active" href="/evidence-approval">Evidence &amp; Approval</Link></nav><GovernancePanel /></main>;
}
