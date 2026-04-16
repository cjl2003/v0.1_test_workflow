# RTL PR 自动审核系统状态说明

## 1. 当前结论

当前仓库已经升级为真正的混合架构：

1. **GitHub Actions + GPT reviewer**
   - 负责读取 PR diff
   - 负责自动 RTL 审核
   - 负责把审核结果评论回 PR

2. **桌面版 Codex**
   - 负责在本机写代码和改代码
   - 负责使用本地 skill
   - 负责本地验证、commit 和 push

也就是说，当前目标已经从“服务器端假装 Codex 修代码”切换为：

- **Codex 本地修复**
- **GPT 云端复审**

这才是现在仓库的正式形态。

## 2. 当前主线上的架构

### 2.1 第一阶段：GPT 自动审核

工作流：

- `.github/workflows/auto-review.yml`

触发条件：

- `pull_request` 的
  - `opened`
  - `synchronize`
  - `reopened`

行为：

- 运行 `tools/reviewer.py`
- 拉取 PR metadata 和 diff
- 调用 review 模型
- 将结果更新到 `RTL Auto Review` 评论

当前 reviewer 的模型配置原则：

- 优先读取 `OPENAI_REVIEW_MODEL`
- 如果未设置，再回退到 `OPENAI_MODEL`

### 2.2 第二阶段：本地桌面 Codex 修复

工作流：

- `.github/workflows/codex-fix.yml`

当前它的职责已经改变：

- 它**不再**在 GitHub Actions 服务器上直接改代码
- 它只负责把 `/codex-fix` 评论转成一个待处理请求

触发条件：

- `issue_comment.created`
- 评论内容以 `/codex-fix` 开头
- 评论者是受信任身份：
  - `OWNER`
  - `MEMBER`
  - `COLLABORATOR`

它会做的事：

1. 确保这些 label 存在：
   - `codex-fix-pending`
   - `codex-fix-applied`
   - `codex-fix-failed`
2. 给对应 PR 打上 `codex-fix-pending`
3. 在 PR 中写一条确认评论，说明请求已经进入本地桌面 Codex 队列

真正修代码的是本地桌面 Codex 自动化，不是 GitHub Actions。

## 3. 当前主线上的关键文件

### 3.1 `tools/reviewer.py`

作用：

- 从环境变量读取：
  - `OPENAI_API_KEY`
  - `GITHUB_TOKEN`
  - `GITHUB_REPO`
- 获取 PR diff
- 调用模型做 RTL 审核
- 回写 PR 评论
- 支持 OpenAI 兼容网关
- 当网关不支持 `responses` 时，可自动降级到 `chat/completions`

### 3.2 `.ai/reviewer_rules.md`

作用：

- 定义 GPT reviewer 的 RTL 审核规则
- 主要覆盖：
  - 顶层接口变化
  - reset 语义
  - 阻塞/非阻塞赋值
  - latch 风险
  - 位宽/符号扩展/截断
  - 可综合性
  - testbench / 验证充分性

### 3.3 `.ai/desktop_codex_fix_rules.md`

作用：

- 定义本地桌面 Codex 修复时必须遵守的边界
- 包括：
  - 只处理 `codex-fix-pending` 的 PR
  - 只修改当前 PR 已改动的文件
  - 优先修 P1 / P2 和 RTL 正确性问题
  - 不做大范围重构
  - 验证失败不 push
  - 失败时给 PR 打 `codex-fix-failed`

## 4. 当前需要的配置

### 4.1 GitHub Secret

必须存在：

- `OPENAI_API_KEY`

### 4.2 GitHub Variables

推荐配置：

- `OPENAI_API_BASE = http://101.43.9.6:3000/v1`
- `OPENAI_REVIEW_MODEL = gpt-5.4`
- `OPENAI_ENDPOINT_STYLE = auto`

可选：

- `OPENAI_MODEL`
- `OPENAI_REASONING_EFFORT`
- `OPENAI_MAX_OUTPUT_TOKENS`
- `MAX_DIFF_CHARS`

说明：

- reviewer 在 GitHub Actions 中使用这些变量
- 本地桌面 Codex 修复**不依赖 GitHub Actions 的 fix 模型变量**

## 5. 现在如何真正工作

### 5.1 PR 自动审核

开发者正常开 PR 后：

1. GitHub 自动触发 `RTL PR Auto Review`
2. GPT reviewer 自动读取 PR diff
3. GPT reviewer 自动给出 RTL 审核评论

这一步是**全自动**的，不需要你额外操作。

### 5.2 请求桌面版 Codex 修复

如果你希望桌面 Codex 自动修：

在 PR 评论里写：

```text
/codex-fix
```

也可以加一句约束：

```text
/codex-fix Please only fix the new RTL file and keep the patch minimal.
```

之后流程是：

1. GitHub 给 PR 打 `codex-fix-pending`
2. 本地桌面 Codex 自动化检测到这个 label
3. 本地桌面 Codex checkout 该 PR 分支
4. 本地桌面 Codex 读取最新 `RTL Auto Review`
5. 本地桌面 Codex 按本地 skill 和 `.ai/desktop_codex_fix_rules.md` 修改代码
6. 本地桌面 Codex 在本机验证
7. 本地桌面 Codex commit 并 push
8. 新 push 触发 GitHub 的 GPT reviewer 再次审查

## 6. 当前已经完成的真实验收

### 6.1 第一阶段自动审核验收

验收 PR：

- `#2`

结论：

- GitHub 自动审核链路已打通

### 6.2 双阶段首个可用版本验收

验收 PR：

- `#5`

结论：

- `/codex-fix` 请求链路已打通
- 能自动生成修复 commit
- 但当时仍是服务器端修复方案

### 6.3 双阶段最终形态验收

旧的“服务器端 Codex 修复”已经被淘汰。

当前主线以“本地桌面 Codex 修复”为准。

后续需要做的真实验收重点是：

1. `/codex-fix` -> `codex-fix-pending`
2. 本地桌面 Codex 自动化捞取该 PR
3. 本地 Codex push 修复 commit
4. GitHub GPT reviewer 自动再次审核

## 7. 当前系统的优点

相较旧方案，当前方案的关键优势是：

1. 真正使用桌面 Codex 本地能力
2. 真正可以使用本地 skill
3. 代码修改发生在本地，不在 GitHub runner 上“伪装成 Codex”
4. GPT reviewer 和 Codex fixer 的角色边界更清晰

## 8. 当前限制

当前仍有限制：

1. 本地桌面 Codex 自动化必须处于开启状态
2. 如果本机关闭，`codex-fix-pending` 的 PR 不会被处理
3. 目前主要支持同仓库 PR
4. reviewer 仍然可能误报或漏报
5. 默认验证命令如果过弱，仍然可能放过不充分修复

## 9. 你现在应该怎么理解它

一句话版本：

- **GitHub 自动审**
- **桌面 Codex 自动修**
- **GitHub 再自动审**

这就是现在这套系统的核心。
