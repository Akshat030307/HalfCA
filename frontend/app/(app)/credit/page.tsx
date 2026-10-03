import { PageHeader } from "@/components/shell/page-header";
import { ComingSoon } from "@/components/system/coming-soon";
import { Chip } from "@/components/ui/chip";

export default function CreditPage() {
  return (
    <>
      <PageHeader
        title="Follow the Credit"
        subtitle="Whose tax credit is your tax credit built on?"
        right={<Chip tone="orange">★ Only on Half CA</Chip>}
      />
      <ComingSoon
        milestone="M4"
        items={[
          "Supplier graph that snaps a 5-firm ring into a circle",
          "Kaveri Metals taint score and ITC at risk",
        ]}
      />
    </>
  );
}
