# Anthropic Workflow Client Design

## Goal

Add Anthropic protocol support to the repository's shared workflow review client so GitHub Actions and local review tools can call Claude through `https://kuaipao.ai` without changing the existing `OPENAI_*` environment variable contract.

This design intentionally keeps the current OpenAI-compatible paths working:

- `responses`
- `chat_completions`
- `auto`

The new work only adds one explicit protocol mode:

- `anthropic_messages`

---

## Why This Change Is Needed

The current repository only knows how to call OpenAI-style endpoints:

- `POST <base>/responses`
- `POST <base>/chat/completions`

That works with OpenAI-compatible bases such as `https://kuaipao.ai/v1`, but it fails against the Claude-oriented root base `https://kuaipao.ai`, which expects Anthropic-style requests instead of OpenAI request shapes.

The operational goal is to let the user switch between GPT-style and Claude-style providers by changing GitHub variables only, not by editing workflow YAML or Python scripts each time.

---

## Scope

### In Scope

- extend the shared client in [`tools/workflow_lib.py`](E:/GitHub/v0.1_test_workflow/tools/workflow_lib.py) with Anthropic protocol dispatch
- expose `anthropic_messages` through `OPENAI_ENDPOINT_STYLE`
- normalize Anthropic base URLs so the user can provide any of these:
  - `https://kuaipao.ai`
  - `https://kuaipao.ai/v1`
  - `https://kuaipao.ai/v1/messages`
- make local reviewer execution in [`tools/reviewer.py`](E:/GitHub/v0.1_test_workflow/tools/reviewer.py) use the same protocol behavior
- add tests for URL normalization, request generation, response parsing, and regression protection for existing OpenAI modes

### Out of Scope

- renaming existing `OPENAI_*` variables to `ANTHROPIC_*`
- changing workflow YAML variable names or secret names
- adding streaming support
- adding Anthropic tool use, images, PDFs, or multi-modal message handling
- changing current PR workflow state machines

---

## User-Facing Configuration Contract

The repository keeps its current environment variable interface:

- `OPENAI_API_KEY`
- `OPENAI_API_BASE`
- `OPENAI_MODEL`
- `OPENAI_REVIEW_MODEL`
- `OPENAI_ENDPOINT_STYLE`
- `OPENAI_REASONING_EFFORT`
- `OPENAI_MAX_OUTPUT_TOKENS`

To use Claude via Anthropic protocol, the user sets:

- `OPENAI_API_BASE=https://kuaipao.ai`
- `OPENAI_ENDPOINT_STYLE=anthropic_messages`
- `OPENAI_MODEL=<claude model>`
- `OPENAI_REVIEW_MODEL=<claude model>`

This keeps workflow YAML stable and limits the protocol switch to repository variables.

---

## Design

### 1. Shared Protocol Dispatch

[`tools/workflow_lib.py`](E:/GitHub/v0.1_test_workflow/tools/workflow_lib.py) becomes the source of truth for protocol dispatch.

The shared caller must support four endpoint styles:

- `responses`
- `chat_completions`
- `anthropic_messages`
- `auto`

Behavior:

- `responses` means force OpenAI Responses API
- `chat_completions` means force OpenAI-compatible chat completions
- `anthropic_messages` means force Anthropic-style messages API
- `auto` keeps the existing OpenAI-first fallback behavior and does **not** infer Anthropic automatically

Reason for keeping `auto` unchanged:

- existing GPT-based workflows should not change behavior silently
- Anthropic mode should be an explicit operator choice

### 2. Anthropic Base URL Normalization

Anthropic mode must normalize `OPENAI_API_BASE` before issuing the request.

Normalization rules:

- if base is `https://kuaipao.ai`, final endpoint is `https://kuaipao.ai/v1/messages`
- if base is `https://kuaipao.ai/v1`, final endpoint is `https://kuaipao.ai/v1/messages`
- if base is `https://kuaipao.ai/v1/messages`, use it as-is
- if base already ends with `/messages`, use it as-is
- trim trailing slashes before normalization

This removes the current manual trial-and-error around provider-specific base forms.

### 3. Anthropic Request Mapping

Anthropic mode uses a standard JSON `messages` request with Anthropic-style headers.

Headers:

- `x-api-key: <OPENAI_API_KEY>`
- `anthropic-version: 2023-06-01`
- `content-type: application/json`

Body:

- `model`
- `max_tokens`
- `system`
- `messages`

Prompt mapping:

- the existing `instructions` string becomes the Anthropic `system` field
- the existing user prompt / review input becomes a single user message in `messages`

Reasoning effort handling:

- `OPENAI_REASONING_EFFORT` is ignored in `anthropic_messages` mode unless the target provider later documents a compatible field
- this avoids sending unknown parameters to Kuaipao's Anthropic-compatible endpoint

### 4. Anthropic Response Mapping

Anthropic mode must extract the final text reply from the standard content array.

Expected source:

- `content[*].text`

Response handling rules:

- concatenate text-bearing content blocks in order
- ignore non-text blocks
- fail clearly if no text blocks are present
- surface HTTP body snippets on errors the same way the current OpenAI paths already do

### 5. Reviewer Reuse

[`tools/reviewer.py`](E:/GitHub/v0.1_test_workflow/tools/reviewer.py) must stop maintaining protocol-specific HTTP details independently.

Target shape:

- reviewer keeps its own diff-fetch and PR-comment logic
- reviewer reuses shared helpers from [`tools/workflow_lib.py`](E:/GitHub/v0.1_test_workflow/tools/workflow_lib.py) for:
  - endpoint-style validation
  - Anthropic URL normalization
  - protocol dispatch
  - response extraction

This avoids future drift where workflow review and local review support different providers or slightly different payloads.

---

## Error Handling

Anthropic mode must fail with operator-readable errors in these cases:

- unsupported endpoint style
- missing API key
- invalid or blank model
- provider returns non-JSON content
- provider returns JSON with no text content
- provider returns HTTP 4xx/5xx

Error messages should preserve the current debugging style:

- include the context of the failing call
- include HTTP status code
- include a bounded response body snippet

The caller should not silently fall back from `anthropic_messages` to OpenAI modes.

---

## Testing

Required automated coverage:

### URL Normalization

- root base normalizes to `/v1/messages`
- `/v1` base normalizes to `/v1/messages`
- `/v1/messages` remains unchanged
- trailing slash variants normalize correctly

### Anthropic Request Construction

- `system` receives the instructions text
- `messages` carries the review input as a user message
- `x-api-key` and `anthropic-version` headers are present
- `max_tokens` maps from `OPENAI_MAX_OUTPUT_TOKENS`

### Anthropic Response Parsing

- single text block extracts correctly
- multiple text blocks concatenate correctly
- empty content raises a clear error

### Regression Coverage

- `responses` path still builds the same request shape
- `chat_completions` path still builds the same request shape
- `auto` behavior stays OpenAI-first with the existing chat-completions fallback

---

## Rollout

After implementation, Claude over Anthropic protocol should be enabled by variables only:

- `OPENAI_API_BASE=https://kuaipao.ai`
- `OPENAI_ENDPOINT_STYLE=anthropic_messages`
- `OPENAI_MODEL=<claude model>`
- `OPENAI_REVIEW_MODEL=<claude model>`

No workflow YAML changes should be required.

Verification should include:

- unit tests
- one minimal local dry-run path if possible
- one GitHub Actions smoke rerun of the existing review workflow against the updated variables

---

## Risks And Mitigations

### Risk 1: Provider-Specific Anthropic Compatibility Gaps

Kuaipao may not behave exactly like Anthropic's public API.

Mitigation:

- keep the Anthropic implementation minimal
- send only the fields required for text completion
- fail loudly on unexpected payload shapes instead of guessing

### Risk 2: Shared Helper Refactor Regresses Existing GPT Flows

Mitigation:

- keep `responses` and `chat_completions` logic intact
- add explicit regression tests around the old modes
- keep `auto` semantics unchanged

### Risk 3: Reviewer And Workflow Paths Drift Again Later

Mitigation:

- centralize protocol-specific logic in shared helpers
- make `reviewer.py` a consumer of that shared path instead of a second implementation

---

## Acceptance Criteria

This design is complete when all of the following are true:

- the repository supports `OPENAI_ENDPOINT_STYLE=anthropic_messages`
- `OPENAI_API_BASE=https://kuaipao.ai` resolves to a working Anthropic-style endpoint
- GitHub workflow review code and local reviewer code use the same Anthropic request/response behavior
- existing OpenAI-style modes continue to work unchanged
- automated tests cover Anthropic normalization and regression boundaries
