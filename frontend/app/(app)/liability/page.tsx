import { PageHeader } from "@/components/shell/page-header";
import { ComingSoon } from "@/components/system/coming-soon";

export default function LiabilityPage() {
  return (
    <>
      <PageHeader
        title="Liability"
        subtitle="What you'll actually owe once the paperwork is honest."
      />
      <ComingSoon
        milestone="M4"
        items={["ITC waterfall and Benford screen", "Net payable: as filed vs reconciled"]}
      />
    </>
  );
}
