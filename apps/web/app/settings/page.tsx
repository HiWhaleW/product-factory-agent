import { getHealth, getMe, getRuntimeStatus } from "@/lib/api";
import { localUser } from "@/lib/identity";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const [health, runtime, session] = await Promise.all([
    getHealth(),
    getRuntimeStatus(),
    getMe(),
  ]);
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
    <main className="page-shell narrow" id="main-content">
      <section className="hero compact">
        <div>
          <p className="eyebrow">INTERNAL SETTINGS</p>
          <h1>配置状态</h1>
          <p className="lead">密钥只显示配置状态，前端永远不接收 API Key 原值。</p>
        </div>
        <span className="status-pill live">API {health.status}</span>
      </section>
      <section aria-labelledby="identity-settings-title" className="identity-settings">
        <header>
          <p className="eyebrow">USER & SESSION / 用户与会话</p>
          <h2 id="identity-settings-title">当前身份</h2>
        </header>
        <div>
          <span aria-hidden="true" className="identity-avatar">我</span>
          <dl>
            <div><dt>角色</dt><dd>{localUser.role}</dd></div>
            <div><dt>Actor ID</dt><dd>{localUser.id}</dd></div>
            <div><dt>运行模式</dt><dd>{localUser.mode}</dd></div>
            <div><dt>身份认证</dt><dd>{session.authenticated ? "会话有效" : localUser.authStatus}</dd></div>
            <div><dt>Session 原因</dt><dd>{session.reason}</dd></div>
            <div><dt>请求强制认证</dt><dd>{session.auth_enforced ? "已启用" : "尚未启用"}</dd></div>
          </dl>
        </div>
        <p>后端已提供邀请码换取 HttpOnly Session、/me 与 logout 契约；当前环境未配置 Session，且业务请求尚未强制认证，因此仍按本机管理员边界展示，不能视为完整登录验收通过。</p>
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
