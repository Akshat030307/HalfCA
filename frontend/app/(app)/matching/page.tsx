import { PageHeader } from "@/components/shell/page-header";
import { ComingSoon } from "@/components/system/coming-soon";

export default function MatchingPage() {
  return (
    <>
      <PageHeader
        title="Matching"
        subtitle="Cheapest rules first. AI only sees the hardest cases."
      />
      <ComingSoon
        milestone="M4"
        items={[
          "Four-stage funnel: exact → normalised → fuzzy → AI",
          "Unmatched queue sorted by ₹ impact",
        ]}
      />
    </>
  );
}
