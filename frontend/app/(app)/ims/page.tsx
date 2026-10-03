import { PageHeader } from "@/components/shell/page-header";
import { ComingSoon } from "@/components/system/coming-soon";

export default function ImsPage() {
  return (
    <>
      <PageHeader
        title="IMS Autopilot"
        subtitle="Accept, reject or hold every supplier invoice before GSTR-2B locks."
      />
      <ComingSoon
        milestone="M4"
        items={["212 supplier records with a reason each", "Approve 197 accepts in one click"]}
      />
    </>
  );
}
