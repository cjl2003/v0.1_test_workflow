# RTL PR 自动审核系统最终状态说明

## 1. 当前结论

当前仓库已经完成并验证了这套混合自动化架构：

1. **GitHub Actions + GPT-5.4 自动审核**
   - PR 创建或更新时自动触发
   - 自动读取 PR diff
   - 自动调用模型做 RTL / Verilog 审核
   - 自动把审核结果写回 PR 评论

2. **桌面版 Codex 本地修复**
   - 在 PR 中评论 `/codex-fix` 后触发排队
   - GitHub 只负责打标签和确认请求
   - 真正的修复发生在本机桌面 Codex
   - 本机修复后自动 push
   - push 之后 GitHub 再自动触发 GPT 复审

一句话理解：

- **GitHub 自动审**
- **桌面 Codex 本地修**
- **GitHub 再自动审**

## 2. 现在主线的真实工作方式

### 2.1 第一阶段：自动审核

工作流：

- `.github/workflows/auto-review.yml`

触发条件：

- `pull_request`
  - `opened`
  - `synchronize`
  - `reopened`

行为：

1. 安装 Python 依赖
2. 运行 `tools/reviewer.py`
3. 读取 PR metadata 和 diff
4. 调用 GPT reviewer
5. 将结果写回同一条 `RTL Auto Review` 评论

### 2.2 第二阶段：Codex 修复请求

工作流：

- `.github/workflows/codex-fix.yml`

触发条件：

- `issue_comment.created`
- 评论内容以 `/codex-fix` 开头
- 评论者是受信任身份：
  - `OWNER`
  - `MEMBER`
  - `COLLABORATOR`

行为：

1. 确保这些标签存在：
   - `codex-fix-pending`
   - `codex-fix-applied`
   - `codex-fix-failed`
2. 给对应 PR 打 `codex-fix-pending`
3. 在 PR 中回复“请求已进入本地桌面 Codex 队列”

注意：

- GitHub Actions **不会**在服务器上直接改代码
- 真正改代码的是本机桌面 Codex

### 2.3 第三阶段：本地桌面 Codex 修复

本地桌面 Codex 自动化负责：

1. 发现带 `codex-fix-pending` 的 PR
2. 读取最新 `RTL Auto Review`
3. checkout 对应 PR 分支
4. 只修改当前 PR 已改过的文件
5. 按 `.ai/desktop_codex_fix_rules.md` 修复
6. 本地验证
7. commit / push
8. 将标签切换为：
   - 成功：`codex-fix-applied`
   - 失败：`codex-fix-failed`

## 3. 当前已验证可用的接入配置

这部分是这次实际验收后确认可用的配置。

### 3.1 GitHub Secret

必须存在：

- `OPENAI_API_KEY`

### 3.2 GitHub Variables

当前已经验证成功的组合是：

- `OPENAI_API_BASE = https://hub.tokenpanda.top/v1`
- `OPENAI_REVIEW_MODEL = gpt-5.4`
- `OPENAI_ENDPOINT_STYLE = chat_completions`

可选变量：

- `OPENAI_MODEL`
- `OPENAI_REASONING_EFFORT`
- `OPENAI_MAX_OUTPUT_TOKENS`
- `MAX_DIFF_CHARS`

### 3.3 关键结论

这次排查已经确认：

1. 当前中转站里的 `gpt-5.4` 是存在的
2. 当前 key 在 `https://hub.tokenpanda.top/v1` 下有效
3. 当前 `gpt-5.4` **支持 `/v1/chat/completions`**
4. 当前网关下直接走 `/v1/responses` 并不稳定

因此当前主线应该固定使用：

- `OPENAI_ENDPOINT_STYLE=chat_completions`

而不是依赖 `auto` 或强制 `responses`

## 4. 当前主线的关键文件

### 4.1 `tools/reviewer.py`

作用：

- 从环境变量读取：
  - `OPENAI_API_KEY`
  - `GITHUB_TOKEN`
  - `GITHUB_REPO`
- 获取 PR diff
- 调用 review 模型
- 回写 PR 评论
- 支持 OpenAI 兼容网关
- 支持：
  - `responses`
  - `chat/completions`

### 4.2 `.ai/reviewer_rules.md`

作用：

- 定义 GPT reviewer 的 RTL 审核规则
- 重点覆盖：
  - 顶层接口变化
  - reset 语义
  - 阻塞/非阻塞赋值
  - latch 风险
  - 位宽/符号扩展/截断
  - 可综合性
  - testbench / 验证充分性

### 4.3 `.ai/desktop_codex_fix_rules.md`

作用：

- 定义本地桌面 Codex 修复时的边界
- 当前关键约束：
  - 只处理 `codex-fix-pending`
  - 只改当前 PR 已改动的文件
  - 优先修 P1 / P2 RTL correctness 问题
  - 不做大范围重构
  - 验证失败不 push

## 5. 本次最终验收记录

### 5.1 自动审核验收

历史验收 PR：

- `#2`

结论：

- GitHub 自动审核链路已打通

### 5.2 双阶段旧版验收

历史验收 PR：

- `#5`

结论：

- `/codex-fix` 请求链路已打通
- 但当时仍是服务器端修复方案

### 5.3 当前最终形态验收

本次最终验收 PR：

- `#9`

在 `#9` 上已经真实验证：

1. GPT-5.4 自动审核成功发表评论
2. `/codex-fix` 成功触发请求队列
3. PR 成功打上 `codex-fix-pending`
4. 本地桌面 Codex 成功修复 RTL 文件
5. 本地修复 commit 已 push
6. 标签成功切换为 `codex-fix-applied`
7. GitHub 成功自动再次运行 GPT reviewer
8. `RTL Auto Review` 评论已更新为修复后的新结果

这说明：

- “桌面 Codex 修复 -> GPT-5.4 再审” 的闭环已经真实跑通

## 6. 当前仍然存在的限制

1. 本地桌面 Codex 自动化必须在这台机器上保持可用
2. 如果本机关闭，`codex-fix-pending` 的 PR 不会被处理
3. 目前主要支持同仓库 PR
4. reviewer 仍然可能误报或漏报
5. 如果本地验证命令太弱，Codex 仍可能提交“语法过关但验证不充分”的修复

## 7. 你现在该怎么用

日常使用方式：

1. 正常开一个 RTL / Verilog PR
2. 等待 GitHub 自动给出 `RTL Auto Review`
3. 如果要让桌面 Codex 尝试修复，就在 PR 评论里写：

```text
/codex-fix
```

4. 等本地 Codex 修复并 push
5. 等 GitHub 自动再次执行 GPT 审核

## 8. 当前最重要的运维提醒

以后如果你再换 key 或换网关，优先检查这三项是否配套：

1. `OPENAI_API_BASE`
2. `OPENAI_API_KEY`
3. `OPENAI_REVIEW_MODEL`

然后确认该模型实际支持的 endpoint 是：

- `/v1/chat/completions`
- 还是 `/v1/responses`

对当前这套中转站和 `gpt-5.4` 来说，已经确认可用的是：

- `chat_completions`
