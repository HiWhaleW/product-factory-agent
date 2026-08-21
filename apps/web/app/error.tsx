"use client";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="page-shell narrow">
      <section className="error-panel">
        <p className="eyebrow">REQUEST FAILED</p>
        <h1>页面暂时不可用</h1>
        <p>真实控制面请求未完成。请重试；如果持续失败，请记录下方错误编号交给维护者核对。</p>
        {error.digest ? <p className="error-reference">错误编号：{error.digest}</p> : null}
        <button onClick={reset} type="button">重试</button>
      </section>
    </main>
  );
}
