# Anthropic Smoke Request

## Goal

Run a minimal request-planning smoke check so the workflow executes the current branch's Anthropic client path through GitHub Actions.

## Scope

- No product change is requested.
- This PR exists only to exercise the workflow model client on the branch head.

## Success Criteria

- The request-planning workflow reaches the model call path with `OPENAI_ENDPOINT_STYLE=anthropic_messages`.
- The workflow returns a JSON API result or a provider-side model/auth error.
- The workflow does not fail because `https://kuaipao.ai` returns homepage HTML.
