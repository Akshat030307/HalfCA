import { PageHeader } from "@/components/shell/page-header";
import { ComingSoon } from "@/components/system/coming-soon";

export default function UploadPage() {
  return (
    <>
      <PageHeader title="Upload" subtitle="Drop the month's files. Half CA sorts out the rest." />
      <ComingSoon
        milestone="M4"
        items={[
          "Five source files slide in: invoices, bank, Tally day book, IMS feed, e-way bills",
          "Live steps: vision extraction, GSTIN checks, normalising, road linking, matching",
          "One click: Use demo dataset",
        ]}
      />
    </>
  );
}
