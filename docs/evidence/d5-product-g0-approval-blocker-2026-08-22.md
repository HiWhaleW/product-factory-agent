# D5 正式项目 G0 批准阻塞记录

> 日期：2026-08-22  
> 用户决定：已明确批准 G0  
> 执行结果：未写入。当前 PostgreSQL 中找不到可安全批准的正式项目 G0。

## 已核验事实

- 当前项目列表只有：D3 双栏交互验收、简历助手、生成一个建立修改助手、D3 PostgreSQL 安装冒烟。
- 唯一 open 的 G0 属于 D3 双栏交互验收。
- 该项目读取 Project Brief v1 返回 PROJECT_BRIEF_NOT_FOUND，事件和消息表明它是 D3 前端验收数据。
- Factory Lead 真实冒烟证据记录的项目 2a3c38e1-9704-4f83-a096-84cb5a5025e7 已不在当前数据库项目列表中。
- 因此没有调用 Gate decision API，没有修改任何项目状态，也没有把测试 G0 当成正式 G0。

## 影响

- 用户的“批准 G0”决定已经收到，但尚未绑定到有效的 Project Brief/Gate。
- AI PM 不能进入正式项目 MRD；Agent Runtime 不应自行重建或代选项目。
- 既有隔离 fixture 的 G0/G1 仍只算测试证据。

## 下一步

用户需确认正式项目名称和一句话目标。确定性服务随后创建或补齐 Project Brief/G0，再把本次人工批准绑定到该 G0。不得批准 D3 双栏交互验收的测试 Gate。
