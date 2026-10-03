import { PageHeader } from "@/components/shell/page-header";
import { ComingSoon } from "@/components/system/coming-soon";

export default function OverviewPage() {
  return (
    <>
      <PageHeader title="Overview" subtitle="September at a glance." />
      <ComingSoon
        milestone="M4"
        items={[
          "Six KPI tiles, ending with exposure caught",
          "Donut, discrepancies by type",
          "Four threads · two invoices",
        ]}
      />
    </>
  );
}
