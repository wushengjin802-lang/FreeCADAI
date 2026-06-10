"use client";

import { Providers } from "@/components/Providers";

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  return <Providers>{children}</Providers>;
}
