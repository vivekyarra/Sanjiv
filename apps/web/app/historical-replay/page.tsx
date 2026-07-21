import { AdvancedDecisionCenter } from "../../components/AdvancedDecisionCenter";

export default async function HistoricalReplayPage({ searchParams }: { searchParams: Promise<{ plan?: string }> }) {
  const { plan } = await searchParams;
  return <AdvancedDecisionCenter initialPlanId={plan ?? ""} />;
}
