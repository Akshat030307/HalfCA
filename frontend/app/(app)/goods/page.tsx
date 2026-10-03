import { PageHeader } from "@/components/shell/page-header";
import { ComingSoon } from "@/components/system/coming-soon";
import { Chip } from "@/components/ui/chip";

export default function GoodsPage() {
  return (
    <>
      <PageHeader
        title="Follow the Goods"
        subtitle="The paper says the goods moved. The road says whether they did."
        right={<Chip tone="orange">★ Only on Half CA</Chip>}
      />
      <ComingSoon
        milestone="M4"
        items={[
          "Road atlas map with four routes and toll plazas",
          "Four beats: verified, paper-only, impossible journey, recycled e-way bill",
        ]}
      />
    </>
  );
}
