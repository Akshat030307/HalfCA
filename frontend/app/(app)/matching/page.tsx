import { MatchingScreen } from "@/components/screens/matching";
import { PageHeader } from "@/components/shell/page-header";

export default function MatchingPage() {
  return (
    <>
      <PageHeader
        title="Matching"
        subtitle="Cheapest rules first. AI only sees the hardest cases."
      />
      <MatchingScreen />
    </>
  );
}
