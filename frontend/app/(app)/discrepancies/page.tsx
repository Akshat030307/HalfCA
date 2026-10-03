import { PageHeader } from "@/components/shell/page-header";
import { ComingSoon } from "@/components/system/coming-soon";

export default function DiscrepanciesPage() {
  return (
    <>
      <PageHeader title="Discrepancies" subtitle="Everything that doesn't add up, with receipts." />
      <ComingSoon
        milestone="M4"
        items={[
          "Three hero flip-cards: abolished slab, wrong tax head, renumbered duplicate",
          "All flags table with a type filter",
        ]}
      />
    </>
  );
}
