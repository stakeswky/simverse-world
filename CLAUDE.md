# Skills-World Project Instructions

## Agent Model Strategy

- **Opus**: Analysis, architecture, code review, planning, brainstorming — all tasks requiring deep reasoning stay on the main thread
- **Sonnet**: Subagent execution — implementation, bug fixes, code generation dispatched to subagents

### Opus→Sonnet→Opus 工作流

```
Opus 分析问题 → 派遣 Sonnet 执行 → Sonnet 返回 → Opus 深度审查 → 通过则提交 / 不通过则派 Sonnet 再改
```

### Opus 审查规范（必须逐项执行）

Sonnet 完成后，Opus **不能**只跑 CI + 看摘要就提交。必须执行以下 4 步：

**Step 1: 逐文件代码审查**
- `Read` 每个被修改的文件，逐行检查变更部分
- 检查点：逻辑正确性、边界情况（空值/越界/类型）、命名一致性、是否引入副作用

**Step 2: 专项检查**
- **竞态/时序**：异步操作之间是否有 race condition（如 WS 消息和 UI 初始化的时序）
- **性能**：是否在热路径（如 Phaser update 每帧调用）中引入 O(n) 遍历或重复计算
- **安全**：用户输入是否经过校验，API 权限是否正确
- **状态一致性**：前后端数据模型是否对齐，store 更新是否覆盖所有路径

**Step 3: 自动化验证**
- 跑 `npx tsc --noEmit`（前端类型检查）
- 跑 `python3 -m pytest tests/`（后端测试）
- 如果改动涉及 WS/实时功能，说明需要手动测试并告知用户

**Step 4: 判定**
- 发现问题 → 明确描述问题 → 派 Sonnet 再改 → 重新审查
- 无问题 → 提交并附带审查要点摘要

**反模式（禁止）：**
- 只跑 CI + 看 Sonnet 摘要就提交（"信任 Sonnet + 跑 CI" 模式）
- 审查时不 Read 源码
- 忽略 Sonnet 摘要中的"也加了 listener"之类模糊描述，不验证具体实现

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL/SQLite
- **Frontend**: React 18 + TypeScript + Phaser 3
- **LLM**: Anthropic SDK (compatible endpoints), Gemini for image gen
- **Testing**: pytest + pytest-asyncio (backend), tsc --noEmit (frontend)

## Working Directory

- Main repo: `/Users/jimmy/Downloads/Skills-World/`
- Active worktree: `.worktrees/mvp-implementation/` (backend + frontend)
- Use `python3` (not `python`) for all commands
- Use `httpx.AsyncClient(trust_env=False)` to bypass local proxy for external API calls

## Key APIs

- SearXNG: `http://100.93.72.102:58080/search` (research)
- LLM: DashScope Anthropic-compatible endpoint
- Image Gen: `http://100.93.72.102:3000/v1` (Gemini Vertex AI)
