"use client";

import type { ReactNode } from "react";
import { AuthProvider } from "@/lib/auth";
import { StoreProvider } from "@/lib/store";

/** Client providers rendered from the server root layout (§13). */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <StoreProvider>{children}</StoreProvider>
    </AuthProvider>
  );
}
