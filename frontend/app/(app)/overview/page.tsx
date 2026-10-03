import { OverviewScreen } from "@/components/screens/overview";
import { PageHeader } from "@/components/shell/page-header";

export default function OverviewPage() {
  return (
    <>
      <PageHeader title="Overview" subtitle="September at a glance." />
      <OverviewScreen />
    </>
  );
}
