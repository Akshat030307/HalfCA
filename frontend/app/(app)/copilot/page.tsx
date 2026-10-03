import { CopilotScreen } from "@/components/screens/copilot";
import { PageHeader } from "@/components/shell/page-header";
import { Chip } from "@/components/ui/chip";

export default function CopilotPage() {
  return (
    <>
      <PageHeader
        title="Copilot"
        subtitle="Ask anything. Every answer shows its working."
        right={<Chip tone="orange">📡 MCP server · 7 tools</Chip>}
      />
      <CopilotScreen />
    </>
  );
}
