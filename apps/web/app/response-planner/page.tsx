import { ResponsePlanner } from "../../components/ResponsePlanner";

export default async function ResponsePlannerPage({ searchParams }: { searchParams: Promise<{ run?: string }> }) {
  const { run } = await searchParams;
  return <ResponsePlanner initialRunId={run ?? ""} />;
}
