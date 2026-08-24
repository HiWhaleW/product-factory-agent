# GitHub Connector 安全快照证据

> 日期：2026-08-23  
> 结果：`completed`  
> 工具：GitHub Connector；未使用 `gh` CLI 或本地 Git push

## 远端事实

- 仓库：`HiWhaleW/product-factory-agent`（private）。
- 默认分支：`main`。
- 工作分支：`codex/initial-import`。
- Draft PR：[PR #1](https://github.com/HiWhaleW/product-factory-agent/pull/1)，状态 `open / draft`。
- 精确父提交：`36503fd9a69d80b4c286c9e92ec07e3446e66da1`。
- 实现快照提交：[db39b5ddfa01e17477c99c6eaa512c5f23422c30](https://github.com/HiWhaleW/product-factory-agent/commit/db39b5ddfa01e17477c99c6eaa512c5f23422c30)。
- 更新方式：`force:false`。
- Compare：ahead 1 / behind 0，merge base 等于精确父提交。
- PR 证据评论 ID：`5381375941`。

## 实际上传清单（31 个 UTF-8 文件）

1. `README.md`
2. `README.html`
3. `apps/api/alembic/versions/20260822_0005_web_projection_contracts.py`
4. `apps/api/alembic/versions/20260822_0006_runtime_projection_backfill.py`
5. `apps/api/app/api/router.py`
6. `apps/api/app/core/config.py`
7. `apps/api/app/domain/models.py`
8. `apps/api/app/domain/schemas.py`
9. `apps/api/app/services/agent_runtime.py`
10. `apps/api/app/services/definition_chain.py`
11. `apps/api/app/services/session_auth.py`
12. `apps/web/app/globals.css`
13. `apps/web/app/projects/[projectId]/artifact-dag.tsx`
14. `apps/web/app/projects/[projectId]/page.tsx`
15. `apps/web/app/projects/[projectId]/workspace-client.tsx`
16. `apps/web/app/settings/page.tsx`
17. `apps/web/lib/api.ts`
18. `apps/web/lib/contracts.ts`
19. `apps/web/lib/workspace.ts`
20. `apps/web/tests/home.test.ts`
21. `apps/web/tests/workspace.test.ts`
22. `tests/agents/test_session_auth.py`
23. `tests/integration/test_definition_chain_postgres.py`
24. `design-qa.md`
25. `design-qa.html`
26. `docs/handoff.md`
27. `docs/handoff.html`
28. `docs/operator-runbook.md`
29. `docs/operator-runbook.html`
30. `docs/evidence/d5-runtime-projection-ego-qa-2026-08-22.json`
31. `docs/evidence/d5-sales-retrospective-product-flow-2026-08-22.json`

## 明确排除

- 秘密/配置：`.env`、`.env.*`、SecretRef 原值、API Key、Token、Bearer 值。
- 运行态：`.runtime/`、Artifact/Workspace 内容、PostgreSQL data、checkpoint、日志。
- 环境/依赖：`.venv/`、`node_modules/`、`.pnpm-store/`、`.uv-cache/`。
- 缓存/构建：`.next/`、`.pytest_cache/`、`.ruff_cache/`、`__pycache__/`、`*.pyc`、`*.tsbuildinfo`。
- 本机配置：`apps/api/alembic.ini`、本机绝对路径与来源路径。
- 大型证据：`.gitignore` 排除的 PNG/PDF 历史截图。
- 本地参考：被 `.gitignore` 标记为 provenance/reference 的手册与规格文件。

## 扫描与保护

候选文件扫描未命中私钥、Provider Key、GitHub Token、Bearer Token、用户 home 绝对路径或 PostgreSQL 本机 data path。Connector commit 以精确父提交创建；分支更新使用 `force:false`，远端并线变化会 fail closed。
