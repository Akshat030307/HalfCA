import { CreditScreen } from "@/components/screens/credit";
import { PageHeader } from "@/components/shell/page-header";
import { Chip } from "@/components/ui/chip";

export default function CreditPage() {
  return (
    <>
      <PageHeader
        title="Follow the Credit"
        subtitle="Your input tax credit is only as real as your supplier's supplier."
        right={<Chip tone="orange">★ Only on Half CA</Chip>}
      />
      <CreditScreen />
    </>
  );
}
