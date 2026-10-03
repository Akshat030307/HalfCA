import { PageHeader } from "@/components/shell/page-header";
import { ComingSoon } from "@/components/system/coming-soon";
import { Chip } from "@/components/ui/chip";

export default function CopilotPage() {
  return (
    <>
      <PageHeader
        title="Copilot"
        subtitle="Ask anything. Every answer shows its working."
        right={<Chip tone="orange">MCP server · 7 tools</Chip>}
      />
      <ComingSoon
        milestone="M4"
        items={["Tool trace, streamed answer, evidence chips", "Works with or without an LLM"]}
      />
    </>
  );
}
