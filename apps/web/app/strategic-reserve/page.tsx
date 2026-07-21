import { StrategicReserve } from "../../components/StrategicReserve";

export default async function StrategicReservePage({ searchParams }: { searchParams: Promise<{ run?: string; plan?: string }> }) {
  const { run, plan } = await searchParams;
  return <StrategicReserve initialRunId={run ?? ""} initialPlanId={plan ?? ""} />;
}
