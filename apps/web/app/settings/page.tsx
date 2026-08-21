import { getHealth, getRuntimeStatus } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const [health, runtime] = await Promise.all([getHealth(), getRuntimeStatus()]);
  const settings = [
    ["模型", `DeepSeek · ${health.model_configured ? "配置待冒烟" : "模型名/Base URL 未配置"}`, "未验证"],
    [
      "Builder",
      runtime.codex.version || "本地 Codex CLI Adapter · 只读检查失败",
      runtime.codex.exit_code === 0 ? "只读检查通过" : "异常",
    ],
    ["数据", `PostgreSQL · ${health.database}`, health.status === "ok" ? "在线" : "异常"],
    ["Artifact Root", runtime.artifact_root_configured ? "本地产物根目录已配置" : "未配置", runtime.artifact_root_configured ? "已加载" : "异常"],
    ["Workspace Root", runtime.workspace_root_configured ? "受限工作区根目录已配置" : "未配置", runtime.workspace_root_configured ? "已加载" : "异常"],
    ["限制", "单并发 · maxTurns 12 · retry 2 · timeout 1800s", "已加载"],
  ];

  return (
    <main className="page-shell narrow">
      <section className="hero compact">
        <div>
          <p className="eyebrow">INTERNAL SETTINGS</p>
          <h1>配置状态</h1>
          <p className="lead">密钥只显示配置状态，前端永远不接收 API Key 原值。</p>
        </div>
        <span className="status-pill live">API {health.status}</span>
      </section>
      <section className="settings-list">
        {settings.map(([name, value, status]) => (
          <article key={name}>
            <strong>{name}</strong>
            <span>{value}</span>
            <span className={["在线", "已加载", "只读检查通过"].includes(status) ? "status-pill live" : "status-pill warning"}>{status}</span>
          </article>
        ))}
      </section>
    </main>
  );
}
