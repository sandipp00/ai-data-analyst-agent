import logging
import time
from functools import lru_cache

from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI

from analyst.config import settings

log = logging.getLogger(__name__)

# How long to skip a model after it fails: a used-up quota (429) won't come back
# soon; overloads and timeouts (503/504) usually clear within minutes.
QUOTA_COOLDOWN_S = 3600
BUSY_COOLDOWN_S = 300

_cooldown_until: dict[str, float] = {}


@lru_cache(maxsize=1)
def get_models() -> list[ChatGoogleGenerativeAI]:
    """The primary model followed by the fallbacks, in order.

    Each Gemini model has its own free-tier quota, so when one runs out (429),
    is overloaded (503) or times out, the next one usually still works.
    """
    names = dict.fromkeys([settings.model, *settings.fallback_models])  # dedupe, keep order
    return [
        ChatGoogleGenerativeAI(
            model=name,
            temperature=0,
            # A failing model is skipped in favour of the next one rather than retried.
            max_retries=0,
            timeout=settings.llm_timeout_s,
            # Free-tier per-minute quotas are per model, so each gets its own pacing
            # (set LLM_REQUESTS_PER_MINUTE higher on a paid plan).
            rate_limiter=InMemoryRateLimiter(
                requests_per_second=settings.requests_per_minute / 60, max_bucket_size=3
            ),
        )
        for name in names
    ]


def _invoke_with_fallback(schema: type, messages):
    models = get_models()
    now = time.monotonic()
    ready = [m for m in models if _cooldown_until.get(m.model, 0) <= now]
    errors = []
    for model in ready or models:  # if every model is cooling down, try them all anyway
        try:
            result = model.with_structured_output(schema).invoke(messages)
        except Exception as e:
            quota = "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e)
            _cooldown_until[model.model] = time.monotonic() + (
                QUOTA_COOLDOWN_S if quota else BUSY_COOLDOWN_S
            )
            log.warning("Model %s failed, trying the next one: %s", model.model, str(e)[:200])
            errors.append(f"{model.model}: {str(e)[:200]}")
            continue
        _cooldown_until.pop(model.model, None)
        return result
    raise RuntimeError("Every model failed:\n" + "\n".join(errors))


def structured_llm(schema: type) -> Runnable:
    """A runnable returning `schema`, trying each available model in turn."""
    return RunnableLambda(lambda messages: _invoke_with_fallback(schema, messages))
