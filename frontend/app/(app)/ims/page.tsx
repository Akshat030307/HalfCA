import { ImsHeaderRight, ImsScreen } from "@/components/screens/ims";
import { PageHeader } from "@/components/shell/page-header";

export default function ImsPage() {
  return (
    <>
      <PageHeader
        title="IMS Autopilot"
        subtitle="Accept, reject or hold every supplier invoice before GSTR-2B locks."
        right={<ImsHeaderRight />}
      />
      <ImsScreen />
    </>
  );
}
