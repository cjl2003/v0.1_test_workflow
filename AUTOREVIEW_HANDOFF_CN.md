# RTL PR 自动审核安装与当前状态说明

## 1. 这次你让我做什么

你最初的目标，是在当前 GitHub 仓库里搭建一个针对 Verilog / RTL 项目的“PR 自动审核”最小系统，要求它能够：

1. 在 pull request 被创建或更新时自动触发。
2. 从 GitHub 读取 PR diff。
3. 调用 OpenAI Responses API 对 RTL / Verilog 改动做审核。
4. 把审核结果作为 PR comment 发回 GitHub。

你随后又要求我继续把这套方案真正落到 Git 仓库，而不是只生成本地文件。具体包括：

1. 把需要的文件真正写入仓库。
2. 检查并补齐 `.github/workflows/auto-review.yml` 里的 `permissions`。
3. 创建分支 `feat/auto-review-bootstrap`。
4. 提交 commit。
5. push 到 GitHub。
6. 创建 PR。
7. 帮你完成 GitHub 登录授权、仓库初始化、PR 创建以及后续测试准备。

## 2. 我已经做到哪一步

截至目前，这套最小系统已经完成安装，且已经真实落到 GitHub 仓库：

- 仓库地址：<https://github.com/cjl2003/v0.1_test_workflow>
- 默认分支：`main`
- 安装 PR：<https://github.com/cjl2003/v0.1_test_workflow/pull/1>
- 安装 PR 状态：已合并
- 自动审核 workflow 已经位于默认分支 `main`
- GitHub Secret `OPENAI_API_KEY` 已经由你手工配置完成

这意味着：

**现在已经可以创建“测试 PR”来验证自动审核是否工作。**

## 3. 这次实际创建了哪些文件

本次为自动审核系统创建了 6 个核心文件：

### 3.1 `.github/workflows/auto-review.yml`

作用：

- 定义 GitHub Actions 工作流。
- 在 `pull_request` 的 `opened` / `synchronize` / `reopened` 事件触发。
- 安装 Python 依赖。
- 从事件中读取 PR 编号。
- 调用 `tools/reviewer.py` 执行审核。

关键点：

- 已包含以下权限：
  - `contents: read`
  - `pull-requests: write`
  - `issues: write`

### 3.2 `tools/reviewer.py`

作用：

- 从环境变量读取：
  - `OPENAI_API_KEY`
  - `GITHUB_TOKEN`
  - `GITHUB_REPO`
- 接收 PR 编号。
- 调用 GitHub REST API 读取 PR metadata 和 unified diff。
- 调用 OpenAI Responses API 进行 RTL 审核。
- 将结果作为 PR comment 回写到 GitHub。
- 对已有自动评论做“更新”而不是每次新发一条。
- 提供异常处理、超时处理和 `--dry-run` 模式。

### 3.3 `requirements.txt`

作用：

- 声明 reviewer 运行所需最小 Python 依赖。

当前依赖：

- `requests`
- `python-dotenv`

### 3.4 `.env.example`

作用：

- 提供本地调试所需环境变量样例。
- 便于后续手工 dry-run 或本地联调。

### 3.5 `.ai/reviewer_rules.md`

作用：

- 定义面向 RTL / Verilog 的审核规则。
- 供 OpenAI 模型在 Responses API 调用时作为高优先级审查规则使用。

覆盖的检查项包括：

- 顶层接口是否意外变更
- reset 语义是否变化
- 阻塞 / 非阻塞赋值是否合理
- 是否可能引入 latch
- 位宽 / 符号扩展 / 截断风险
- 可综合性
- testbench 和验证是否充分

### 3.6 `README_AUTOREVIEW.md`

作用：

- 说明这套系统做什么。
- 说明需要配置哪些 GitHub Secrets。
- 说明如何首次启用。
- 说明如何测试。
- 说明如何扩展为“Codex 修复 -> GPT 再审”。

## 4. 这次还额外创建了什么

为了给你留档，我又新增了这一份中文说明文档：

- `AUTOREVIEW_HANDOFF_CN.md`

它不是自动审核系统运行所必需的文件，但能帮助你以后快速回顾当前状态和操作方法。

## 5. 我实际执行了哪些步骤

下面是本次实际完成的操作过程。

### 5.1 在本地工作目录生成自动审核文件

我先在当前目录中创建了以下结构：

- `.github/workflows/auto-review.yml`
- `tools/reviewer.py`
- `requirements.txt`
- `.env.example`
- `.ai/reviewer_rules.md`
- `README_AUTOREVIEW.md`

并确认 `reviewer.py` 具备：

- 环境变量读取
- PR diff 拉取
- OpenAI Responses API 调用
- GitHub PR 评论回写
- 注释和异常处理

### 5.2 本地做了基础验证

我执行过以下基础验证：

1. `python -m py_compile tools/reviewer.py`
2. `python tools/reviewer.py --help`

这些用于确认脚本语法、导入路径和 CLI 入口正常。

### 5.3 初始化本地 Git 仓库

因为你当前目录一开始不是 git 仓库，我执行了：

1. `git init -b main`
2. 创建本地初始提交
3. 创建分支 `feat/auto-review-bootstrap`

### 5.4 完成本地提交

我完成了两次本地提交：

1. `chore: initialize repository`
2. `feat: add RTL PR auto-review bootstrap`

### 5.5 完成 GitHub CLI 登录与授权

这台机器一开始没有可直接用的 GitHub CLI，会导致无法自动建远端仓库和 PR。为此我做了：

1. 下载并安装 `gh` CLI 到本机目录。
2. 拉起 GitHub 设备登录流程。
3. 引导你完成 GitHub 网页授权。
4. 验证 `gh auth status` 登录成功。

### 5.6 创建远端 GitHub 仓库

在登录成功后，我实际创建了远端仓库：

- `cjl2003/v0.1_test_workflow`

并完成：

1. 绑定 `origin`
2. push `feat/auto-review-bootstrap`
3. push `main`

### 5.7 创建并合并安装 PR

我创建了安装 PR：

- PR #1
- 标题：`feat: add RTL PR auto-review bootstrap`

随后又完成：

1. 将 PR #1 合并到 `main`
2. 将仓库默认分支设置为 `main`

这样后续新的测试 PR 才会使用到 `main` 上已经存在的 workflow 文件。

### 5.8 你完成了 Secret 配置

你后来已经在 GitHub 仓库里成功配置：

- `OPENAI_API_KEY`

这一步是自动审核真正可调用 OpenAI API 的前提条件。

## 6. 当前仓库是什么状态

当前状态可以概括为：

- 代码和 workflow 已经在 `main`
- 远端仓库已经存在
- `OPENAI_API_KEY` 已经存在
- 安装 PR 已经合并
- 自动审核系统已经具备运行条件

因此当前真正缺少的，不再是“安装”，而是：

**创建一个测试 PR，用来触发并验证自动审核。**

## 7. 接下来应该怎么做

接下来建议按下面顺序做。

### 7.1 创建一个最小测试分支

从 `main` 拉一个新分支，例如：

- `test/smoke-review`

### 7.2 提交一个很小的 RTL 文件改动

最简单的做法是：

- 新增一个很小的 `.v` 文件
- 或者修改一个已有 `.v` / `.sv` 文件

建议测试内容尽量简单，这样方便判断 reviewer 是否真的看到了 diff。

### 7.3 在 GitHub 网页创建测试 PR

把测试分支提交到 GitHub 后，创建：

- base: `main`
- compare: `test/smoke-review`

### 7.4 等待 workflow 跑完

创建 PR 后，仓库中的 `RTL PR Auto Review` workflow 应该被触发。

### 7.5 在 PR 页查看结果

你需要看两个位置：

1. `Checks` / `Actions`
   - 看 workflow 是否成功执行
2. `Conversation`
   - 看是否出现 `RTL Auto Review` 评论

## 8. 如果测试没有成功，优先检查什么

如果测试 PR 没有得到预期结果，建议按这个顺序检查：

### 8.1 看 workflow 是否触发

如果 PR 创建后完全没有 workflow：

- 先确认 PR 的 base 是 `main`
- 再确认 workflow 文件仍在 `main`

### 8.2 看 workflow 是否执行失败

如果 workflow 被触发但失败：

- 打开 GitHub Actions 日志
- 看是哪个步骤失败

常见失败点包括：

- `OPENAI_API_KEY` 配置错误
- GitHub token 权限不足
- OpenAI API 请求失败
- reviewer 脚本异常退出

### 8.3 看 PR 评论是否写回成功

如果脚本跑了但 PR 没有评论：

- 查看 `issues: write` / `pull-requests: write` 权限
- 查看 GitHub Actions 日志里是否有 comment API 错误

## 9. 关于“PR 到底是什么意思”

PR = Pull Request。

可以把它理解为：

> “我在一个分支里做了改动，现在请求把这些改动合并到目标分支（通常是 `main`）里。”

一个 PR 一般包含：

1. 改了哪些文件
2. 代码差异 diff
3. 自动化检查结果
4. 审查评论
5. 最后是否合并

本项目现在的自动审核机制，就是在 PR 这个节点上运行的。

## 10. 本项目里自动审核的工作方式

当前系统的逻辑是：

1. 你创建 PR
2. GitHub Actions 收到 `pull_request` 事件
3. workflow 调用 `tools/reviewer.py`
4. `reviewer.py` 向 GitHub API 读取 PR diff
5. `reviewer.py` 把 diff 和 `.ai/reviewer_rules.md` 一起发给 OpenAI Responses API
6. OpenAI 返回中文审核结果
7. `reviewer.py` 把结果评论回 PR

如果同一个 PR 后续又 push 了新 commit：

1. 会再次触发 `synchronize`
2. reviewer 会重新获取最新 diff
3. 自动更新之前的机器人评论

## 11. 你现在真正需要做的事

对你来说，下一步只需要做一件事：

**创建一个测试 PR。**

如果你希望，我下一轮可以继续做下面两种帮助中的任意一种：

1. 继续用中文一步一步教你在 GitHub 网页上创建最小测试 PR。
2. 直接在本地再帮你创建一个测试分支、提交一个最小 Verilog 文件，并自动 push，然后再帮你开测试 PR。

## 12. 安全提醒

这次对话过程中，你曾发送过 GitHub 账号密码。

虽然我没有使用它，但仍建议你尽快：

1. 修改 GitHub 密码
2. 检查 GitHub 的登录记录和安全日志
3. 确认没有异常设备或异常授权应用

这不是自动审核系统的一部分，但从安全角度值得马上处理。
