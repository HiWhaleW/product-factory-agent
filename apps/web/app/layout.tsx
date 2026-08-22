import type { Metadata } from "next";
import type { ReactNode } from "react";

import { GlobalHeader } from "@/app/global-header";
import { OnboardingGuide } from "@/app/onboarding-guide";

import "@xyflow/react/dist/style.css";
import "./globals.css";

const productName = process.env.NEXT_PUBLIC_PRODUCT_NAME?.trim() || "造物工场";

export const metadata: Metadata = {
  title: productName,
  description: "从真实想法到可追溯交付链的产品工场",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <GlobalHeader productName={productName} />
        {children}
        <OnboardingGuide />
      </body>
    </html>
  );
}
