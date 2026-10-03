"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

// The static export has no server redirects; send visitors to the first screen.
export default function Home() {
  const router = useRouter();
  useEffect(() => router.replace("/upload/"), [router]);
  return (
    <main className="grid min-h-screen place-items-center">
      <Link href="/upload/" className="font-display text-2xl uppercase text-orange">
        Open Half CA →
      </Link>
    </main>
  );
}
