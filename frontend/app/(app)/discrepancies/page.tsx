import { Suspense } from "react";

import { DiscrepanciesScreen } from "@/components/screens/discrepancies";
import { PageHeader } from "@/components/shell/page-header";
import { Skeleton } from "@/components/ui/states";

export default function DiscrepanciesPage() {
  return (
    <>
      <PageHeader title="Discrepancies" subtitle="Everything that doesn't add up, with receipts." />
      {/* useSearchParams needs a Suspense boundary in a static export */}
      <Suspense fallback={<Skeleton className="h-[640px]" />}>
        <DiscrepanciesScreen />
      </Suspense>
    </>
  );
}
