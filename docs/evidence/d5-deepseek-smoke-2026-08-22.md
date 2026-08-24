# D5 DeepSeek 真实冒烟记录

> 日期：2026-08-22（Asia/Shanghai）  
> 结论：部分通过，不满足 D5 完整纵向切片放行条件  
> 安全口径：未记录密钥、Prompt 原文或模型输出原文；仅保留请求 ID、哈希、字符数、Token 和延迟

## 1. 环境与实现事实

- `.env` 中 `MODEL_PROVIDER`、`MODEL_NAME`、HTTPS `MODEL_BASE_URL`、`MODEL_API_KEY_REF` 和对应 Secret 值均已就绪。
- 配置模型名为 `deepseek-chat`；流式响应元数据报告的实际服务模型为 `deepseek-v4-flash`，该别名/路由差异尚未解释。
- 新增异步 DeepSeek Adapter，覆盖 SecretRef、认证、超时、429、上下文过长、严格 JSON Schema、工具调用和 SSE。
- Adapter 只返回模型结果，不持有 Project、Context、Gate、Permission 或幂等状态；模型输出不能直接推进业务状态。

## 2. 真实冒烟结果

| 用例 | 状态 | 延迟 | 已知 Token | 证据/限制 |
|---|---|---:|---:|---|
| 认证与网络 | 通过 | 985 ms | 9 | 官方端点接受 SecretRef；只保存输出哈希 |
| SSE 流式 | 通过 | 993 ms | 39 | 收到多个 delta；响应元数据显示 `deepseek-v4-flash` |
| 强制工具调用 | 通过 | 839 ms | 376 | 工具名与 JSON 参数符合声明 Schema；未执行业务副作用 |
| JSON Schema | 通过 | 1276 ms | 126 | JSON mode 通过本地 Pydantic 严格校验 |
| 中文长文档 | 通过 | 890 ms | 8353 | 输入 13,391 个中文字符；输出仅保留哈希与长度 |
| 强制超时 | 通过 | 21 ms | 未产生可用量 | 1 ms deadline 被归类为 `DEEPSEEK_TIMEOUT`，fail closed |
| Context too long | **失败** | 1681 ms | 未记录 | 约 28 万字符输入未触发可识别的超长拒绝；不能声称该错误路径已真实验证 |
| 真实 429 | 未观察 | 0 ms | 0 | 未用请求洪泛制造限流；429/Retry-After 仅有 MockTransport 单测 |

已记录用例合计 Token 为 8,903；context-too-long 用例可能产生额外 Token，但当前冒烟器未记录该成功响应的 Usage。所有用例 `estimated_cost_cny` 均为 `null`，费用映射尚未实现。

## 3. 自动测试

- `tests/agents/test_deepseek_adapter.py`：8 项 Adapter 契约测试通过。
- 覆盖：SecretRef 缺失、认证错误脱敏、结构化输出、Schema 拒绝、工具参数、SSE usage、超时、429 与 context-too-long 类型化。
- 本报告不等于 LangGraph、Factory Lead、AI PM、Builder 或 Reviewer 的真实运行验收。

## 4. 失败与过程问题

1. 第一次冒烟命令缺少 `PYTHONPATH=apps/api`，以 `ModuleNotFoundError: No module named 'app'` 失败；补齐模块路径后运行成功。
2. `uv lock` 第一次在受限网络中因 PyPI DNS 解析失败；获准联网后重新解析 60 个包并成功更新锁文件。
3. 超长上下文没有被供应商拒绝，可能是输入仍在实际上下文上限内，也可能存在服务端压缩/路由；在确认模型实际上下文限制前不继续盲目扩大付费请求。
4. 配置名与返回模型名不一致，需要按 DeepSeek 实际路由文档或供应商响应进一步确认。

## 5. 未完成与下一步

- 将 Adapter 接入最小 Agent Runtime/Run Journal，而不是从 Prompt 直接调用业务写 API。
- 用真实 Factory Lead 跑“模糊输入 → 澄清 → Brief/G0”，再用 AI PM 跑“Evidence/MRD/G1”。
- 记录 Prompt/Skill/Context 版本、真实引用、首次 Schema 合规、重试、Token、延迟与费用。
- 为 context-too-long 增加不扩大实际费用的边界方法；真实 429 保持未观察，不使用请求洪泛测试。
- 当前短轮询仍是降级通道；完整 AG-UI 长连接与浏览器断线恢复尚未验证。

## 6. HTML 验证状态

同名 HTML 阅读版已用 ego-browser 真实检查 `1440×900` 与 `390×844`：两种视口均无页面级横向溢出；移动端结果表在自身容器内横向滚动。该检查只证明本报告可读，不代表产品 Web 视觉验收通过。
