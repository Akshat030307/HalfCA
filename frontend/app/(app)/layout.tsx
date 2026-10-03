import { EvidenceProvider } from "@/components/evidence/evidence-drawer";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <EvidenceProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <main className="mx-auto w-full max-w-[1600px] flex-1 px-8 py-8">{children}</main>
        </div>
      </div>
    </EvidenceProvider>
  );
}
