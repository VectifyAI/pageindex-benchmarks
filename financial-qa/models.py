"""The 35 configurations benchmarked: a model on OpenRouter, the provider it is pinned to, and a reasoning level."""

# key: (name, vendor, OpenRouter model, provider, level, effort). `effort` is the reasoning.effort sent; None sends
# no reasoning setting, so the model runs at its default level, which is `level` (METHOD.md, "Reasoning levels").
# MiMo models have no levels; Muse Wonder's default is a level the model picks for itself ("adaptive").
CONFIGS = {
    "claude-opus-5.5-max": ("Claude Opus 5.5", "Anthropic", "anthropic/claude-opus-5.5", "Anthropic", "max", "max"),
    "claude-opus-5.5-medium": ("Claude Opus 5.5", "Anthropic", "anthropic/claude-opus-5.5", "Anthropic", "medium", None),
    "claude-sonnet-5.5-max": ("Claude Sonnet 5.5", "Anthropic", "anthropic/claude-sonnet-5.5", "Anthropic", "max", "max"),
    "claude-sonnet-5.5-high": ("Claude Sonnet 5.5", "Anthropic", "anthropic/claude-sonnet-5.5", "Anthropic", "high", None),
    "claude-haiku-5.5-max": ("Claude Haiku 5.5", "Anthropic", "anthropic/claude-haiku-5.5", "Anthropic", "max", "max"),
    "claude-haiku-5.5-medium": ("Claude Haiku 5.5", "Anthropic", "anthropic/claude-haiku-5.5", "Anthropic", "medium", None),
    "gpt-6.1-sol-max": ("GPT-6.1 Sol", "OpenAI", "openai/gpt-6.1-sol", "OpenAI", "max", "max"),
    "gpt-6.1-sol-medium": ("GPT-6.1 Sol", "OpenAI", "openai/gpt-6.1-sol", "OpenAI", "medium", None),
    "gpt-6.1-sol-low": ("GPT-6.1 Sol", "OpenAI", "openai/gpt-6.1-sol", "OpenAI", "low", "low"),
    "gpt-6-luna-max": ("GPT-6 Luna", "OpenAI", "openai/gpt-6-luna", "OpenAI", "max", "max"),
    "gpt-6-luna-medium": ("GPT-6 Luna", "OpenAI", "openai/gpt-6-luna", "OpenAI", "medium", None),
    "gemini-4-argon-high": ("Gemini 4 Argon", "Google", "google/gemini-4-argon", "Google AI Studio", "high", "high"),
    "gemini-4-argon-medium": ("Gemini 4 Argon", "Google", "google/gemini-4-argon", "Google AI Studio", "medium", None),
    "gemini-3.8-flash-high": ("Gemini 3.8 Flash", "Google", "google/gemini-3.8-flash", "Google AI Studio", "high", "high"),
    "gemini-3.8-flash-medium": ("Gemini 3.8 Flash", "Google", "google/gemini-3.8-flash", "Google AI Studio", "medium", None),
    "muse-wonder-max": ("Muse Wonder", "Meta", "meta/muse-wonder", "Meta", "max", "max"),
    "muse-wonder-adaptive": ("Muse Wonder", "Meta", "meta/muse-wonder", "Meta", "adaptive", None),
    # no first-party endpoint; Together serves it at Meta's list price, unquantized
    "muse-spark-open-xhigh": ("Muse Spark Open", "Meta", "meta/muse-spark-open", "Together", "xhigh", None),
    "grok-4.7-xhigh": ("Grok 4.7", "SpaceXAI", "x-ai/grok-4.7", "xAI", "xhigh", "xhigh"),
    "grok-4.7-high": ("Grok 4.7", "SpaceXAI", "x-ai/grok-4.7", "xAI", "high", None),
    # Together serves this snapshot at DeepSeek's list price
    "deepseek-v4.1-flash-max": ("DeepSeek V4.1 Flash", "DeepSeek", "deepseek/deepseek-v4.1-flash-1017", "Together", "max", "max"),
    "deepseek-v4.1-flash-high": ("DeepSeek V4.1 Flash", "DeepSeek", "deepseek/deepseek-v4.1-flash-1017", "Together", "high", None),
    "qwen3.8-max-xhigh": ("Qwen3.8 Max", "Alibaba", "qwen/qwen3.8-max-0902", "Alibaba", "xhigh", None),
    "qwen3.8-27b-xhigh": ("Qwen3.8 27B", "Alibaba", "qwen/qwen3.8-27b", "Alibaba", "xhigh", None),
    "glm-5.3-max": ("GLM-5.3", "Z AI", "z-ai/glm-5.3", "Z.AI", "max", None),
    "glm-5.3-flash-max": ("GLM-5.3-Flash", "Z AI", "z-ai/glm-5.3-flash", "Z.AI", "max", None),
    "kimi-k3-max": ("Kimi K3", "Kimi", "moonshotai/kimi-k3", "Moonshot AI", "max", None),
    "kimi-k3.1-pro-max": ("Kimi K3.1 Pro", "Kimi", "moonshotai/kimi-k3.1-pro", "Moonshot AI", "max", "max"),
    "minimax-m3.1-flash-max": ("MiniMax M3.1 Flash", "MiniMax", "minimax/minimax-m3.1-flash", "Minimax", "max", "max"),
    "minimax-m3.1-flash-xhigh": ("MiniMax M3.1 Flash", "MiniMax", "minimax/minimax-m3.1-flash", "Minimax", "xhigh", "xhigh"),
    "minimax-m3.1-flash-high": ("MiniMax M3.1 Flash", "MiniMax", "minimax/minimax-m3.1-flash", "Minimax", "high", "high"),
    "minimax-m3.1-flash-medium": ("MiniMax M3.1 Flash", "MiniMax", "minimax/minimax-m3.1-flash", "Minimax", "medium", "medium"),
    "minimax-m3.1-flash-low": ("MiniMax M3.1 Flash", "MiniMax", "minimax/minimax-m3.1-flash", "Minimax", "low", "low"),
    "mimo-v2.6-pro": ("MiMo-V2.6-Pro", "Xiaomi", "xiaomi/mimo-v2.6-pro", "Xiaomi", None, None),
    "mimo-v2.6-flash": ("MiMo-V2.6-Flash", "Xiaomi", "xiaomi/mimo-v2.6-flash", "Xiaomi", None, None),
}


def label(key):
    """'Claude Opus 5.5 (max)', or the bare name for a model without levels."""
    name, *_, level, _ = CONFIGS[key]
    return f"{name} ({level})" if level else name
