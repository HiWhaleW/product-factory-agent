import { LoginForm } from "@/app/login-form";
import { ApiKeySettings } from "@/app/settings/api-key-settings";
import { getMe, getProviderCredential } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const session = await getMe();
  if (session.auth_enforced && !session.authenticated) {
    return (
      <main className="page-shell narrow" id="main-content">
        <section className="hero compact"><div><p className="eyebrow">API SETTINGS</p><h1>请先登录</h1></div></section>
        <section className="workshop-panel auth-panel" aria-label="登录"><LoginForm /></section>
      </main>
    );
  }
  const credential = await getProviderCredential();
  return (
    <main className="page-shell narrow" id="main-content">
      <section className="hero compact">
        <div><p className="eyebrow">API SETTINGS / API 设置</p><h1>让 Agent 使用你的 API</h1><p className="lead">添加专属于你的API Key，让Agent 为你的项目执行真实任务。</p></div>
      </section>
      <ApiKeySettings initialStatus={credential} />
    </main>
  );
}
