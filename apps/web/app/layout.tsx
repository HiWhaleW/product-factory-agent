import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";

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
        <header className="global-header">
          <Link className="brand" href="/">
            <Image alt="" aria-hidden="true" height={40} priority src="/workshop-mark.png" width={40} />
            <span>{productName}</span>
          </Link>
          <nav aria-label="主导航">
            <Link href="/">项目</Link>
            <Link href="/settings">设置</Link>
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
