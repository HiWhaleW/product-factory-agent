import Link from "next/link";

import { getMe } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const session = await getMe();
  return (
    <main className="page-shell home-page" id="main-content">
      <section className="home-hero home-welcome">
        <p className="eyebrow">PRODUCT WORKSHOP / AI NATIVE PRODUCT DELIVERY</p>
        <h1>{session.authenticated ? `你好，${session.display_name ?? "欢迎回来"}` : "把真实目标交给你的 Agent 团队"}</h1>
        <p>进入项目页告诉 Agent 你的目标，由它读取上下文、推进任务、生成产物并等待你决定关键 Gate。</p>
      </section>
      <section aria-label="开始使用" className="home-actions">
        <Link href="/projects"><span>01 / PROJECTS</span><strong>进入项目列表</strong><p>查看已有项目，或从一个真实想法创建新项目。</p></Link>
        <Link href="/settings"><span>02 / API KEY</span><strong>配置模型接口</strong><p>添加专属于你的 API Key，让 Agent 执行真实任务。</p></Link>
      </section>
    </main>
  );
}
