import { LoginForm } from "@/app/login-form";
import { ApiKeySettings } from "@/app/settings/api-key-settings";
import { CodexRuntimeSettings } from "@/app/settings/codex-runtime-settings";
import { ResearchApiSettings } from "@/app/settings/research-api-settings";
import {
  getCodexRuntimeCapability,
  getMe,
  getProviderCredential,
  getResearchCredential,
} from "@/lib/api";

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
  const [credential, codexCapability, researchCredential] = await Promise.all([
    getProviderCredential(),
    getCodexRuntimeCapability(),
    getResearchCredential(),
  ]);
  return (
    <main className="page-shell narrow" id="main-content">
      <section className="hero compact">
        <div><p className="eyebrow">API SETTINGS / API 设置</p><h1>让 Agent 使用你的 API</h1><p className="lead">产品不提供任何 API，请分别添加你的大模型 API 和网络搜索 API。</p></div>
      </section>
      <ApiKeySettings initialStatus={credential} />
      <CodexRuntimeSettings initialStatus={codexCapability} />
      <ResearchApiSettings initialStatus={researchCredential} />
    </main>
  );
}
