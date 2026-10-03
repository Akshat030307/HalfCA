export type NavItem = {
  letter: string;
  href: string;
  label: string;
  star?: boolean;
};

export const NAV: NavItem[] = [
  { letter: "A", href: "/upload/", label: "Upload" },
  { letter: "B", href: "/matching/", label: "Matching" },
  { letter: "C", href: "/overview/", label: "Overview" },
  { letter: "D", href: "/discrepancies/", label: "Discrepancies" },
  { letter: "E", href: "/goods/", label: "Follow the Goods", star: true },
  { letter: "F", href: "/credit/", label: "Follow the Credit", star: true },
  { letter: "G", href: "/ims/", label: "IMS Autopilot" },
  { letter: "H", href: "/liability/", label: "Liability" },
  { letter: "I", href: "/copilot/", label: "Copilot" },
];
