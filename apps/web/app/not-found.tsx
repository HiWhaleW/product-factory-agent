import Link from "next/link";

export default function NotFoundPage() {
  return (
    <main className="page-shell narrow">
      <section className="error-panel">
        <p className="eyebrow">404</p>
        <h1>项目不存在</h1>
        <p>没有找到对应的真实项目记录。它可能已失效，或地址并不完整。</p>
        <Link className="primary-link" href="/">返回项目列表</Link>
      </section>
    </main>
  );
}
