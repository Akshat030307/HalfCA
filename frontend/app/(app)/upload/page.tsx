import { UploadScreen } from "@/components/screens/upload";
import { PageHeader } from "@/components/shell/page-header";

export default function UploadPage() {
  return (
    <>
      <PageHeader title="Upload" subtitle="Drop the month's files. Half CA sorts out the rest." />
      <UploadScreen />
    </>
  );
}
