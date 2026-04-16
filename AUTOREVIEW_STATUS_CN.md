# RTL PR 自动审核系统状态说明

## 1. 当前结论

当前仓库已经具备可用的 Verilog/RTL PR 自动审核能力，并且已经完成一次真实验证。

已满足的目标：

1. 当 PR 被创建或更新时，自动触发 reviewer
2. reviewer 从 GitHub 读取 PR diff
3. reviewer 调用大模型接口做 RTL/Verilog 审核
4. reviewer 把结果作为 PR comment 回写到 GitHub

## 2. 当前仓库状态

- 仓库地址：`https://github.com/cjl2003/v0.1_test_workflow`
- 默认分支：`main`
- bootstrap PR：`#1`，已合并
- 主线修复 PR：`#3`，已合并
- 测试 PR：`#2`，已创建且 workflow 已成功运行

关键验证结果：

- PR `#2` 的 GitHub Actions workflow 已成功触发并通过
- PR `#2` 页面已经出现自动审核评论
- 评论内容为真实 RTL 审核结果，不再是失败占位提示

## 3. 当前主线上的关键实现

主线 `main` 已包含以下能力：

- `.github/workflows/auto-review.yml`
  - 在 `pull_request` 的 `opened` / `synchronize` / `reopened` 触发
  - 包含权限：
    - `contents: read`
    - `issues: write`
    - `pull-requests: write`
  - 自动安装 Python 依赖并运行 `tools/reviewer.py`
  - 从 GitHub event 中获取 PR number

- `tools/reviewer.py`
  - 从环境变量读取：
    - `OPENAI_API_KEY`
    - `GITHUB_TOKEN`
    - `GITHUB_REPO`
  - 通过 GitHub API 拉取 PR metadata 与 diff
  - 调用模型接口执行 RTL 审核
  - 将结果以可更新评论写回 PR
  - 包含异常处理、失败评论回写、清晰日志
  - 支持 OpenAI 兼容网关
  - 当 `responses` 端点不可用时，可自动回退到 `chat/completions`

- `tests/test_reviewer.py`
  - 覆盖默认值回退
  - 覆盖评论失败格式
  - 覆盖 chat completions 文本提取
  - 覆盖网关回退逻辑

## 4. 当前使用的仓库配置

### 4.1 GitHub Secret

必须存在：

- `OPENAI_API_KEY`

### 4.2 GitHub Actions Variables

当前已配置：

- `OPENAI_API_BASE = http://101.43.9.6:3000/v1`
- `OPENAI_ENDPOINT_STYLE = auto`
- `OPENAI_MODEL = claude-sonnet-4-6`

说明：

- 当前仓库并不是直接调用 OpenAI 官方接口，而是通过你指定的 OpenAI 兼容网关
- reviewer 会优先尝试 `responses`
- 如果网关返回“不支持该请求形态”，会自动降级到 `chat/completions`

## 5. 本次实际完成的工作

### 5.1 bootstrap 安装

已经创建并写入以下核心文件：

- `.github/workflows/auto-review.yml`
- `tools/reviewer.py`
- `requirements.txt`
- `.env.example`
- `.ai/reviewer_rules.md`
- `README_AUTOREVIEW.md`

### 5.2 GitHub 仓库初始化与接入

已经完成：

- 本地建仓
- 创建功能分支
- commit
- push
- 创建 bootstrap PR
- 合并 bootstrap PR 到 `main`

### 5.3 联调与排障

已经完成：

- 修复 GitHub Actions 中空环境变量导致默认值失效的问题
- 增加 reviewer 失败时的 PR 状态评论
- 增加 OpenAI 兼容网关支持
- 增加 responses -> chat completions 自动回退
- 增加单元测试覆盖

### 5.4 实测验证

已经完成：

- 创建测试分支
- 创建测试 PR `#2`
- 在 `rtl/smoke_counter.v` 中故意保留易识别 RTL 问题
- 触发 workflow
- 确认 PR 页面收到自动审核评论

## 6. 测试 PR 为什么能证明系统可用

测试文件 `rtl/smoke_counter.v` 中保留了一个典型 RTL 问题：

- 在时序逻辑中使用阻塞赋值 `=`

自动 reviewer 在 PR 评论中已经识别出这类问题，并给出中文审查意见。这证明以下链路都已经跑通：

1. GitHub PR 事件触发成功
2. workflow 成功运行
3. reviewer 成功拿到 diff
4. reviewer 成功调用模型接口
5. reviewer 成功把结果评论回 GitHub

## 7. 你后续如何使用

以后你的日常使用方式非常简单：

1. 从 `main` 拉一个新分支
2. 修改你的 `.v` / `.sv` / RTL 相关文件
3. push 分支
4. 创建 PR 到 `main`
5. 等待 GitHub Actions 自动跑完
6. 在 PR 的 `Conversation` 页面查看自动审核评论

## 8. 你现在通常只需要看哪几个地方

在 GitHub 网页上，主要看这 3 个地方：

1. `Pull requests`
2. 进入目标 PR 的 `Conversation`
3. 进入目标 PR 的 `Checks` 或 `Actions`

## 9. 如果后面又失败，优先检查什么

优先检查：

1. `OPENAI_API_KEY` 是否仍然有效
2. `OPENAI_API_BASE` 是否还是正确网关地址
3. `OPENAI_MODEL` 是否仍是网关支持的模型名
4. workflow 的 `permissions` 是否被误改
5. PR comment API 是否因 token 权限不足而失败

## 10. 当前建议

当前系统已经可以投入“最小可用”状态使用。

建议后续做两件事：

1. 保留 PR `#2` 作为验收样例，或者在确认后手动关闭它
2. 后续如果要做“Codex 修复 -> GPT 再审”，可以在现有 reviewer 基础上再增加一个修复 workflow
