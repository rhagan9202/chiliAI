# Theme 4 — Harden LLM Fallback Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure JSON-decode failures from any LLM adapter surface as `LlmProviderError`, so the `FallbackLlmClient` correctly tries the next provider in the chain instead of letting `json.JSONDecodeError` escape and break it.

**Architecture:** `FallbackLlmClient.generate` only catches `LlmProviderError`. The Ollama adapter currently calls `httpx.Response.json()` outside any try/except — a 2xx response with a non-JSON body (Ollama can return one if streaming-by-mistake or returns an HTML error page) raises `json.JSONDecodeError`, escapes the fallback's catch, and aborts the chain. Fix is local to `OllamaLlmClient`: wrap the parse and re-raise as `LlmProviderError`. OpenAI and Anthropic adapters use their official SDKs (no raw `response.json()`) and are already safe.

**Tech Stack:** Python 3.12, httpx, pytest, `unittest.mock.patch`

**Dependencies on other themes:** None. Theme 4 is independent and can ship at any time.

---

## File Structure

**Modify:**
- `backend/llm/adapters/ollama_adapter.py:54` — wrap `response.json()` with try/except → `LlmProviderError`

**Test additions (modify existing files, do NOT create new ones):**
- `backend/tests/llm/test_ollama_adapter.py` — add test for non-JSON 200 response
- `backend/tests/llm/test_fallback_client.py` — add composition test using real `OllamaLlmClient` with httpx mocked

**No new files. No new exception types. The existing `LlmProviderError` is the correct exception class.**

---

## Task 1: Audit OpenAI and Anthropic adapters for raw `response.json()` usage

**Files:**
- Read-only audit: `backend/llm/adapters/openai_adapter.py`, `backend/llm/adapters/anthropic_adapter.py`

- [ ] **Step 1: Run the audit grep**

```bash
grep -n "response.json\|httpx\.Response\|JSONDecode" backend/llm/adapters/openai_adapter.py backend/llm/adapters/anthropic_adapter.py
```

Expected: no matches in either file. Both adapters use their official SDKs (`openai`, `anthropic`) which deserialize responses internally and wrap parse failures in SDK exceptions that the adapter code already maps to `LlmProviderError`.

- [ ] **Step 2: Document the audit result**

If the grep above returns matches, STOP and report them — those would need wrapping too. If it returns nothing, this task is complete; no production code changes for OpenAI/Anthropic in this theme.

- [ ] **Step 3: No commit**

This task is a verification gate, not a code change. Move to Task 2.

---

## Task 2: Add failing test that Ollama returning non-JSON 200 raises `LlmProviderError`

**Files:**
- Modify: `backend/tests/llm/test_ollama_adapter.py` (currently 72 lines; append at end)

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/llm/test_ollama_adapter.py`:

```python
def test_generate_raises_on_non_json_body() -> None:
    response = httpx.Response(status_code=200, text="<html>nginx 502</html>")
    with patch.object(httpx.Client, "post", return_value=response):
        client = OllamaLlmClient(base_url="http://localhost:11434")
        with pytest.raises(LlmProviderError):
            client.generate(_request())


def test_generate_raises_on_partial_json_body() -> None:
    response = httpx.Response(status_code=200, text='{"message": {"content": "hi"')
    with patch.object(httpx.Client, "post", return_value=response):
        client = OllamaLlmClient(base_url="http://localhost:11434")
        with pytest.raises(LlmProviderError):
            client.generate(_request())
```

These mirror the existing `test_generate_raises_on_5xx` pattern (line 38) and add coverage for the malformed-body case the spec calls out.

- [ ] **Step 2: Run the new tests and verify they fail**

```bash
cd backend && pytest tests/llm/test_ollama_adapter.py::test_generate_raises_on_non_json_body tests/llm/test_ollama_adapter.py::test_generate_raises_on_partial_json_body -v
```

Expected: both FAIL. The error class will be `json.JSONDecodeError` (or equivalent from `httpx`), not `LlmProviderError`. Pytest reports something like:

```
DID NOT RAISE <class 'llm.exceptions.LlmProviderError'>
```

Or pytest may report the unhandled `JSONDecodeError` itself bubbling up. Either confirms the bug.

- [ ] **Step 3: Do not commit yet**

The failing test is the spec. Implementation in Task 3.

---

## Task 3: Wrap `response.json()` in `OllamaLlmClient.generate`

**Files:**
- Modify: `backend/llm/adapters/ollama_adapter.py:54`

- [ ] **Step 1: Apply the fix**

In `backend/llm/adapters/ollama_adapter.py`, replace lines 53-57 (the block that decodes the response body):

Current code:

```python
        if response.status_code >= 400:
            raise LlmProviderError(
                f"Ollama rejected request ({response.status_code}): {response.text[:200]}"
            )

        body = response.json()
        completion = body.get("message", {}).get("content", "")
        if not completion.strip():
            raise LlmProviderError("Ollama returned an empty completion.")
```

Replace with:

```python
        if response.status_code >= 400:
            raise LlmProviderError(
                f"Ollama rejected request ({response.status_code}): {response.text[:200]}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise LlmProviderError(
                f"Ollama returned non-JSON body: {response.text[:200]}"
            ) from exc

        completion = body.get("message", {}).get("content", "")
        if not completion.strip():
            raise LlmProviderError("Ollama returned an empty completion.")
```

Note: `httpx.Response.json()` raises `json.JSONDecodeError` which is a `ValueError` subclass; catching `ValueError` is the conventional Python idiom and avoids importing `json` solely for the exception type. The body prefix is truncated to 200 chars matching the existing 4xx/5xx error pattern at lines 47-52.

- [ ] **Step 2: Run the previously-failing tests**

```bash
cd backend && pytest tests/llm/test_ollama_adapter.py::test_generate_raises_on_non_json_body tests/llm/test_ollama_adapter.py::test_generate_raises_on_partial_json_body -v
```

Expected: both PASS.

- [ ] **Step 3: Run the full Ollama adapter test file**

```bash
cd backend && pytest tests/llm/test_ollama_adapter.py -v
```

Expected: all 7 tests PASS (5 original + 2 new). No regressions on `test_generate_calls_ollama_chat_endpoint`, `test_generate_raises_on_5xx`, `test_generate_raises_on_4xx`, `test_generate_raises_on_empty_completion`, `test_generate_raises_on_transport_error`.

- [ ] **Step 4: Commit**

```bash
cd backend && git add llm/adapters/ollama_adapter.py tests/llm/test_ollama_adapter.py
git commit -m "$(cat <<'EOF'
fix(llm): wrap Ollama response.json() so decode errors surface as LlmProviderError

httpx.Response.json() raises ValueError (JSONDecodeError) on malformed
bodies, which bypassed FallbackLlmClient's LlmProviderError catch and
aborted the fallback chain when Ollama returned a non-JSON 2xx (e.g.,
proxy HTML, truncated streaming response).
EOF
)"
```

---

## Task 4: Add fallback-chain composition test using real `OllamaLlmClient`

**Why this task exists:** The Ollama-level fix (Task 3) is sufficient on its own, but the spec asks for a test confirming the fallback chain actually falls through when the primary adapter would otherwise have leaked a decode error. The existing `test_fallback_client.py` uses `MagicMock` primaries — that doesn't exercise the integration between the two layers. This task adds one composition test.

**Files:**
- Modify: `backend/tests/llm/test_fallback_client.py` (currently 86 lines; append at end)

- [ ] **Step 1: Add the composition test**

Append to `backend/tests/llm/test_fallback_client.py`:

```python
from unittest.mock import patch  # noqa: E402 — add at top of file with existing imports
import httpx  # noqa: E402

from llm.adapters.ollama_adapter import OllamaLlmClient


def test_fallback_used_when_ollama_primary_returns_non_json() -> None:
    """The fallback chain must tolerate adapter-level decode failures.

    Regression guard for the bug where Ollama's `response.json()` raised
    `ValueError` outside any try/except, causing `FallbackLlmClient` (which
    only catches `LlmProviderError`) to abort the chain instead of falling
    through.
    """
    bad_response = httpx.Response(status_code=200, text="<html>nginx 502</html>")
    primary = OllamaLlmClient(base_url="http://localhost:11434")

    fallback = MagicMock()
    fallback.generate.return_value = _result("fallback-1")

    client = FallbackLlmClient(primary=primary, fallbacks=[fallback])

    with patch.object(httpx.Client, "post", return_value=bad_response):
        result = client.generate(_request())

    assert result.metadata.provider == "fallback-1"
    fallback.generate.assert_called_once()
```

**Import additions:** the top of `test_fallback_client.py` currently imports only `MagicMock` from `unittest.mock`. Add `patch` to that import line and add the two new module imports above. Final import block at top of file:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from llm.adapters.fallback import FallbackLlmClient
from llm.adapters.ollama_adapter import OllamaLlmClient
from llm.exceptions import LlmProviderError
from llm.models import (
    ChatMessage,
    CompletionMetadata,
    GenerationRequest,
    GenerationResult,
    MessageRole,
)
```

(Drop the inline `# noqa` comments — they're not needed once the imports are consolidated at the top.)

- [ ] **Step 2: Run the new test**

```bash
cd backend && pytest tests/llm/test_fallback_client.py::test_fallback_used_when_ollama_primary_returns_non_json -v
```

Expected: PASS. The Ollama adapter (post-Task 3) wraps the decode error as `LlmProviderError`, the fallback catches it, and the next client serves the request.

- [ ] **Step 3: Run the full fallback test file**

```bash
cd backend && pytest tests/llm/test_fallback_client.py -v
```

Expected: all 5 tests PASS (4 original + 1 new).

- [ ] **Step 4: Commit**

```bash
cd backend && git add tests/llm/test_fallback_client.py
git commit -m "$(cat <<'EOF'
test(llm): fallback chain falls through on Ollama JSON-decode failure

Composition test wiring a real OllamaLlmClient as primary with httpx
mocked; verifies FallbackLlmClient hands off to the next provider when
the primary returns a non-JSON 200. Regression guard for the wrapping
fix in the previous commit.
EOF
)"
```

---

## Task 5: Final verification — full LLM suite + coverage gate

**Files:** none (read-only verification)

- [ ] **Step 1: Run the full LLM test suite with coverage**

```bash
cd backend && pytest tests/llm/ --cov=llm --cov-report=term-missing
```

Expected:
- All tests PASS.
- Coverage on `llm/adapters/ollama_adapter.py` is ≥ 85% (the new tests exercise the new branch).
- Coverage on `llm/adapters/fallback.py` is ≥ 85%.
- Overall `llm/` coverage ≥ 85% per the project's coverage gate.

If coverage drops below 85% on any file, add a focused test for the uncovered lines before continuing.

- [ ] **Step 2: Run pyright on touched files**

```bash
cd backend && pyright llm/adapters/ollama_adapter.py tests/llm/test_ollama_adapter.py tests/llm/test_fallback_client.py
```

Expected: 0 errors, 0 warnings. The `try/except ValueError` block does not introduce any `Any` leaks.

- [ ] **Step 3: Run ruff**

```bash
cd backend && ruff check llm/adapters/ollama_adapter.py tests/llm/test_ollama_adapter.py tests/llm/test_fallback_client.py
```

Expected: no findings.

- [ ] **Step 4: Confirm no other adapter has the same bug**

```bash
grep -n "response\.json()" backend/llm/adapters/*.py
```

Expected: only `ollama_adapter.py` matches, and the match is now inside the try block we added in Task 3.

- [ ] **Step 5: No commit (verification only)**

If any step above fails, fix it in the touched file and re-run. The end state has two commits on this branch: the Ollama wrap fix and the fallback composition test.

---

## Acceptance Criteria — Sign-off Checklist

- [ ] `backend/llm/adapters/ollama_adapter.py` wraps `response.json()` in a `try/except ValueError` block that raises `LlmProviderError` with a truncated body prefix.
- [ ] `backend/tests/llm/test_ollama_adapter.py` contains two new tests covering non-JSON and partial-JSON bodies; both pass.
- [ ] `backend/tests/llm/test_fallback_client.py` contains a composition test using a real `OllamaLlmClient` as primary; it passes.
- [ ] `pytest tests/llm/ --cov=llm` shows ≥ 85% coverage.
- [ ] `pyright` and `ruff check` clean on the touched files.
- [ ] `grep "response.json()" backend/llm/adapters/*.py` shows only the in-try-block usage in `ollama_adapter.py`.

## Scope Discipline

This theme is intentionally narrow.

- **Do NOT** broaden `FallbackLlmClient.generate`'s `except LlmProviderError` to `except Exception`. The spec marks that as an optional future hardening; doing it here loses error-class precision and isn't necessary once Task 3 lands.
- **Do NOT** add retry/backoff jitter to OpenAI/Anthropic adapters. That's a separate item in Theme 6.
- **Do NOT** change `GenerationRequest.max_tokens` default. Also Theme 6.
- **Do NOT** add a streaming method to the protocol. Out of scope.
