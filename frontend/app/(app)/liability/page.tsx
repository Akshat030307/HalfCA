import { LiabilityScreen } from "@/components/screens/liability";
import { PageHeader } from "@/components/shell/page-header";

export default function LiabilityPage() {
  return (
    <>
      <PageHeader
        title="Liability"
        subtitle="What you'll actually owe once the paperwork is honest."
      />
      <LiabilityScreen />
    </>
  );
}
