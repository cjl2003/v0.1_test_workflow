# RTL PR 自动审核系统最终状态说明

## 1. 当前结论

当前仓库已经具备一套可运行、已落地、已做真实验证的 Verilog/RTL PR 自动审核系统，并且已经扩展为手动触发的双阶段闭环：

1. PR 创建或更新时自动进行 RTL 审核
2. 审核结果自动评论回 GitHub PR
3. 人工在 PR 中评论 `/codex-fix` 后，触发自动修复
4. 自动修复完成后，在同一个 workflow 内立即再次执行 reviewer，刷新 PR 审核评论

这套系统现在已经达到“最小可用”状态。

## 2. 当前仓库状态

- 仓库地址：`https://github.com/cjl2003/v0.1_test_workflow`
- 默认分支：`main`
- 当前主线状态：`main` 与 `origin/main` 已同步

当前与本系统相关的关键 PR 状态：

- `#1` bootstrap 安装 PR：已合并
- `#3` reviewer 稳定性修复 PR：已合并
- `#4` 手动 Codex 修复 workflow PR：已合并
- `#6` “修复后立即再审”热修 PR：已合并
- `#2` 第一阶段自动审核验收 PR：已关闭，作为验收记录保留
- `#5` 双阶段 workflow 首个可用版本验收 PR：已关闭，作为验收记录保留
- `#7` 双阶段 workflow 最终形态验收 PR：已关闭，作为最终验收记录保留

## 3. 当前主线上的工作流

### 3.1 第一阶段：自动审核

文件：

- `.github/workflows/auto-review.yml`

作用：

- 在 `pull_request` 的以下事件触发：
  - `opened`
  - `synchronize`
  - `reopened`
- 安装 Python 依赖
- 运行 `tools/reviewer.py`
- 从 GitHub event 获取 PR number
- 拉取 PR diff
- 调用模型做 RTL 审核
- 将审查结果作为 PR comment 回写到 GitHub

权限：

- `contents: read`
- `issues: write`
- `pull-requests: write`

### 3.2 第二阶段：手动 Codex 修复并立即再审

文件：

- `.github/workflows/codex-fix.yml`

作用：

- 在 `issue_comment` 的 `created` 事件触发
- 只接受以下受信任评论者：
  - `OWNER`
  - `MEMBER`
  - `COLLABORATOR`
- 只在评论内容以 `/codex-fix` 开头时执行
- checkout 当前 PR 分支
- 运行 `tools/codex_fix.py`
- 若修复成功并 push 了新 commit，则在同一个 workflow 里等待几秒，然后立即再次运行 `tools/reviewer.py`
- 刷新 PR 上的 `RTL Auto Review` 评论

权限：

- `contents: write`
- `issues: write`
- `pull-requests: write`

## 4. 当前主线上的核心脚本

### 4.1 `tools/reviewer.py`

作用：

- 从环境变量读取：
  - `OPENAI_API_KEY`
  - `GITHUB_TOKEN`
  - `GITHUB_REPO`
- 读取 PR metadata 和 PR diff
- 调用模型接口执行 RTL 审核
- 将结果写回 PR
- 若审核失败，也会回写失败状态评论，避免 workflow 失败但 PR 页面没有信息
- 支持 OpenAI 兼容网关
- 当网关不支持 `responses` 时，可自动回退到 `chat/completions`

### 4.2 `tools/codex_fix.py`

作用：

- 从 PR 评论中解析 `/codex-fix`
- 读取该 PR 上最新的 `RTL Auto Review` 评论
- 只允许修改“当前 PR 已改动的 UTF-8 文本文件”
- 请求模型输出受约束的 JSON 修复结果
- 将模型返回的完整文件内容写回工作区
- 运行最小验证命令
- 成功后 commit 并 push 回 PR 分支
- 将修复状态写回 PR 的 `RTL Auto Fix` 评论

当前的安全边界：

- 只支持同仓库 PR，不支持跨仓库 fork PR
- 只允许修改本 PR 已改动的文件
- 只允许修改能按 UTF-8 读取的文本文件
- 默认验证命令是 `git diff --check`

## 5. 当前仓库配置

### 5.1 GitHub Secret

必须存在：

- `OPENAI_API_KEY`

### 5.2 GitHub Actions Variables

当前已配置并在使用：

- `OPENAI_API_BASE = http://101.43.9.6:3000/v1`
- `OPENAI_ENDPOINT_STYLE = auto`
- `OPENAI_MODEL = claude-sonnet-4-6`

当前支持但可选的变量：

- `OPENAI_FIX_MODEL`
- `OPENAI_REASONING_EFFORT`
- `OPENAI_MAX_OUTPUT_TOKENS`
- `MAX_DIFF_CHARS`
- `MAX_FIX_CONTEXT_CHARS`
- `CODEX_FIX_VERIFY_COMMAND`

说明：

- 当前不是直接走 OpenAI 官方接口，而是走你指定的 OpenAI 兼容网关
- reviewer 和 fixer 都可复用同一套网关配置

## 6. 真实验收记录

### 6.1 第一阶段自动审核验收

验收 PR：

- `#2`

验证内容：

- PR 创建后自动触发 `RTL PR Auto Review`
- reviewer 能正确拉取 PR diff
- reviewer 能调用模型接口
- reviewer 能将 RTL 审核评论回写到 PR 页面

结果：

- 已通过
- PR 已关闭，作为验收记录保留

### 6.2 双阶段 workflow 首个可用版本验收

验收 PR：

- `#5`

验证内容：

- 第一阶段自动审核正常
- `/codex-fix` 能触发 `RTL PR Codex Fix`
- fixer 能自动提交修复 commit
- PR 页面能收到 `RTL Auto Fix` 评论

结果：

- 已通过
- 该 PR 对应的是“首个可用版本”
- 后续 `#6` 已把“修复后立即再审”补进主线
- PR 已关闭，作为阶段性验收记录保留

### 6.3 双阶段 workflow 最终形态验收

验收 PR：

- `#7`

验证内容：

- 第一阶段 `RTL Auto Review` 正常触发
- 手动 `/codex-fix` 正常触发第二阶段
- fixer 自动生成并 push 修复 commit
- PR 页面收到 `RTL Auto Fix` 评论
- `codex-fix.yml` 在修复后立即再次运行 `tools/reviewer.py`
- `RTL Auto Review` 评论被刷新

结果：

- 已通过
- PR 已关闭，作为最终验收记录保留

## 7. 现在如何使用

以后正常使用时，流程如下：

1. 从 `main` 拉一个新分支
2. 修改你的 `.v` / `.sv` / RTL 相关文件
3. push 分支
4. 创建 PR 到 `main`
5. 等待 `RTL PR Auto Review` 自动完成
6. 在 PR 的 `Conversation` 中查看 `RTL Auto Review` 评论
7. 如果你希望机器人尝试修复，就在 PR 中评论：

```text
/codex-fix
```

也可以附带一句约束，例如：

```text
/codex-fix Please only fix the new RTL file and keep the change minimal.
```

8. 等待 `RTL PR Codex Fix` 完成
9. 查看：
   - `RTL Auto Fix` 评论
   - 被刷新后的 `RTL Auto Review` 评论

## 8. GitHub 网页上你主要看哪里

平时主要看这几个地方：

1. `Pull requests`
2. 目标 PR 的 `Conversation`
3. 目标 PR 的 `Checks`
4. 仓库的 `Actions`

## 9. 当前已知限制

这套系统已经可用，但仍有明确边界：

1. 当前 auto-fix 只支持同仓库 PR，不支持 fork PR
2. 当前 auto-fix 只处理“该 PR 已改动”的文本文件，不会跨文件大范围重构
3. 默认验证命令较弱，只做 `git diff --check`
4. 模型的再审结论仍可能存在误报、漏报或理解偏差
5. 因此当前系统更适合做“辅助审核 / 辅助修复”，不适合直接自动合并

## 10. 如果后续失败，优先检查什么

优先检查：

1. `OPENAI_API_KEY` 是否仍有效
2. `OPENAI_API_BASE` 是否仍是可用网关地址
3. `OPENAI_MODEL` / `OPENAI_FIX_MODEL` 是否仍是网关支持的模型名
4. workflow `permissions` 是否被误改
5. `RTL Auto Review` 或 `RTL Auto Fix` 评论是否有失败原因
6. `CODEX_FIX_VERIFY_COMMAND` 是否过严或失效

## 11. 当前建议

当前系统已经可以投入日常最小使用。

建议下一步优先做下面两件事中的至少一件：

1. 将 `CODEX_FIX_VERIFY_COMMAND` 升级为更有意义的 RTL 检查命令，例如 lint、语法检查或最小仿真
2. 为 `codex_fix.py` 增加“最大循环次数”和“只修复最新 findings”的更严格约束
