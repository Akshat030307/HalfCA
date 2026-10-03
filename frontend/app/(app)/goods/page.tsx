import { GoodsScreen } from "@/components/screens/goods";
import { PageHeader } from "@/components/shell/page-header";
import { Chip } from "@/components/ui/chip";

export default function GoodsPage() {
  return (
    <>
      <PageHeader
        title="Follow the Goods"
        subtitle="The paper says the goods moved. The road says whether they did."
        right={<Chip tone="orange">★ Only on Half CA</Chip>}
      />
      <GoodsScreen />
    </>
  );
}
