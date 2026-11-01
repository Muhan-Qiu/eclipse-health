"""LLM 服务商预设（A7）。

设计原则：

- 预设只是「填表助手」：用户选服务商、填 Key（必要时再选模型），不用查文档填 base URL；
- ``litellm_provider`` 是模型字符串的前缀，必须能在当前 LiteLLM 版本里被
  ``get_llm_provider`` 解析；无法确认的厂商统一走 ``openai`` + 官方 OpenAI 兼容地址；
- 预设里不包含任何真实 Key，也不包含遥测字段；
- ``baseUrl`` 为 ``None`` 表示交给 LiteLLM / 云 SDK 自己解析默认端点
  （Gemini、Bedrock、Vertex AI、Azure 这类不能写死单一地址的厂商）。

数据同时供后端 ``ProviderStore`` 校验和前端设置页渲染使用，字段统一为 camelCase。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

# 分组顺序与前端展示顺序一致。
GROUPS: Final[tuple[str, ...]] = (
    "official",
    "china",
    "gateway",
    "local",
    "custom",
    "demo",
)


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    id: str
    label: str
    label_en: str
    kind: str  # Provider.kind：openai / anthropic / ollama / mock
    litellm_provider: str | None
    base_url: str | None
    default_model: str
    models: tuple[str, ...]
    needs_key: bool
    key_url: str | None
    docs_url: str | None
    description: str
    description_en: str
    group: str
    requires_base_url: bool = False
    local: bool = False
    custom: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "labelEn": self.label_en,
            "kind": self.kind,
            "litellmProvider": self.litellm_provider,
            "baseUrl": self.base_url,
            "defaultModel": self.default_model,
            "models": list(self.models),
            "needsKey": self.needs_key,
            "keyUrl": self.key_url,
            "docsUrl": self.docs_url,
            "description": self.description,
            "descriptionEn": self.description_en,
            "group": self.group,
            "requiresBaseUrl": self.requires_base_url,
            "local": self.local,
            "custom": self.custom,
        }


_PRESETS: Final[tuple[ProviderPreset, ...]] = (
    # ------------------------------------------------------------------ #
    # 官方 / 国际云
    # ------------------------------------------------------------------ #
    ProviderPreset(
        id="openai",
        label="OpenAI",
        label_en="OpenAI",
        kind="openai",
        litellm_provider="openai",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4.1-mini",
        models=("gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "o4-mini"),
        needs_key=True,
        key_url="https://platform.openai.com/api-keys",
        docs_url="https://docs.litellm.ai/docs/providers/openai",
        description="OpenAI 官方 API，兼容最好的工具调用实现。",
        description_en="Official OpenAI API with the most mature tool-calling support.",
        group="official",
    ),
    ProviderPreset(
        id="anthropic",
        label="Anthropic",
        label_en="Anthropic",
        kind="anthropic",
        litellm_provider="anthropic",
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-5",
        models=("claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5-20251001"),
        needs_key=True,
        key_url="https://console.anthropic.com/settings/keys",
        docs_url="https://docs.litellm.ai/docs/providers/anthropic",
        description="Anthropic Claude 官方 API，长上下文与工具调用稳定。",
        description_en="Official Anthropic Claude API with stable long-context tool use.",
        group="official",
    ),
    ProviderPreset(
        id="gemini",
        label="Google Gemini",
        label_en="Google Gemini",
        kind="openai",
        litellm_provider="gemini",
        base_url=None,
        default_model="gemini-2.5-flash",
        models=("gemini-2.5-flash", "gemini-2.5-pro"),
        needs_key=True,
        key_url="https://aistudio.google.com/app/apikey",
        docs_url="https://docs.litellm.ai/docs/providers/gemini",
        description="Google AI Studio 的 Gemini API，端点由官方 SDK 解析。",
        description_en="Gemini via Google AI Studio; the endpoint is resolved by the official SDK.",
        group="official",
    ),
    ProviderPreset(
        id="azure-openai",
        label="Azure OpenAI",
        label_en="Azure OpenAI",
        kind="openai",
        litellm_provider="azure",
        base_url=None,
        default_model="gpt-4.1-mini",
        models=(),
        needs_key=True,
        key_url="https://portal.azure.com/",
        docs_url="https://docs.litellm.ai/docs/providers/azure",
        description="需要填写资源端点（https://<资源名>.openai.azure.com）并在「模型」里填部署名。",
        description_en=(
            "Set the resource endpoint (https://<resource>.openai.azure.com) and use the "
            "deployment name as the model."
        ),
        group="official",
        requires_base_url=True,
    ),
    ProviderPreset(
        id="bedrock",
        label="AWS Bedrock",
        label_en="AWS Bedrock",
        kind="openai",
        litellm_provider="bedrock",
        base_url=None,
        default_model="anthropic.claude-3-5-sonnet-20241022-v2:0",
        models=(
            "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "amazon.nova-pro-v1:0",
        ),
        needs_key=True,
        key_url="https://console.aws.amazon.com/bedrock/home#/api-keys",
        docs_url="https://docs.litellm.ai/docs/providers/bedrock",
        description="使用 Bedrock API Key；区域由 AWS_REGION_NAME 或实例默认区域决定。",
        description_en=(
            "Uses a Bedrock API key; the region comes from AWS_REGION_NAME or the default "
            "AWS region."
        ),
        group="official",
    ),
    ProviderPreset(
        id="vertex-ai",
        label="Google Vertex AI",
        label_en="Google Vertex AI",
        kind="openai",
        litellm_provider="vertex_ai",
        base_url=None,
        default_model="gemini-2.5-flash",
        models=("gemini-2.5-flash", "gemini-2.5-pro"),
        needs_key=True,
        key_url="https://console.cloud.google.com/apis/credentials",
        docs_url="https://docs.litellm.ai/docs/providers/vertex",
        description=(
            "支持 Vertex AI Express 模式 API Key；也可改用 GOOGLE_APPLICATION_CREDENTIALS "
            "服务账号（此时 Key 可留任意占位值）。"
        ),
        description_en=(
            "Supports a Vertex AI Express-mode API key, or GOOGLE_APPLICATION_CREDENTIALS "
            "with a service account (any placeholder key works then)."
        ),
        group="official",
    ),
    ProviderPreset(
        id="mistral",
        label="Mistral",
        label_en="Mistral",
        kind="openai",
        litellm_provider="mistral",
        base_url="https://api.mistral.ai/v1",
        default_model="mistral-large-latest",
        models=("mistral-large-latest", "mistral-small-latest", "codestral-latest"),
        needs_key=True,
        key_url="https://console.mistral.ai/api-keys",
        docs_url="https://docs.litellm.ai/docs/providers/mistral",
        description="Mistral 官方 API。",
        description_en="Official Mistral API.",
        group="official",
    ),
    ProviderPreset(
        id="xai",
        label="xAI Grok",
        label_en="xAI Grok",
        kind="openai",
        litellm_provider="xai",
        base_url="https://api.x.ai/v1",
        default_model="grok-4",
        models=("grok-4", "grok-3", "grok-3-mini"),
        needs_key=True,
        key_url="https://console.x.ai/",
        docs_url="https://docs.litellm.ai/docs/providers/xai",
        description="xAI Grok 官方 API。",
        description_en="Official xAI Grok API.",
        group="official",
    ),
    ProviderPreset(
        id="perplexity",
        label="Perplexity",
        label_en="Perplexity",
        kind="openai",
        litellm_provider="perplexity",
        base_url="https://api.perplexity.ai",
        default_model="sonar-pro",
        models=("sonar-pro", "sonar", "sonar-reasoning-pro"),
        needs_key=True,
        key_url="https://www.perplexity.ai/settings/api",
        docs_url="https://docs.litellm.ai/docs/providers/perplexity",
        description="Perplexity Sonar API；模型自带联网检索。",
        description_en="Perplexity Sonar API; models include built-in web search.",
        group="official",
    ),
    # ------------------------------------------------------------------ #
    # 国内服务商
    # ------------------------------------------------------------------ #
    ProviderPreset(
        id="deepseek",
        label="DeepSeek",
        label_en="DeepSeek",
        kind="openai",
        litellm_provider="deepseek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        models=("deepseek-chat", "deepseek-reasoner"),
        needs_key=True,
        key_url="https://platform.deepseek.com/api_keys",
        docs_url="https://docs.litellm.ai/docs/providers/deepseek",
        description="DeepSeek 官方 API，OpenAI 兼容。",
        description_en="Official DeepSeek API, OpenAI-compatible.",
        group="china",
    ),
    ProviderPreset(
        id="moonshot",
        label="Moonshot / Kimi",
        label_en="Moonshot / Kimi",
        kind="openai",
        litellm_provider="moonshot",
        base_url="https://api.moonshot.cn/v1",
        default_model="moonshot-v1-8k",
        models=("moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"),
        needs_key=True,
        key_url="https://platform.moonshot.cn/console/api-keys",
        docs_url="https://docs.litellm.ai/docs/providers/moonshot",
        description="月之暗面 Kimi 国内站；国际站可在「高级」里改成 api.moonshot.ai/v1。",
        description_en=(
            "Moonshot China endpoint; switch the base URL to api.moonshot.ai/v1 for the "
            "international site."
        ),
        group="china",
    ),
    ProviderPreset(
        id="zhipu",
        label="智谱 GLM",
        label_en="Zhipu GLM",
        kind="openai",
        litellm_provider="zai",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-4.6",
        models=("glm-4.6", "glm-4.5", "glm-4-flash"),
        needs_key=True,
        key_url="https://open.bigmodel.cn/usercenter/apikeys",
        docs_url="https://docs.litellm.ai/docs/providers/zai",
        description="智谱开放平台；LiteLLM 前缀为 zai，国际站可在「高级」里改成 api.z.ai。",
        description_en=(
            "Zhipu open platform; LiteLLM prefix is zai. Switch to api.z.ai in Advanced "
            "for the international site."
        ),
        group="china",
    ),
    ProviderPreset(
        id="dashscope",
        label="通义千问 / DashScope",
        label_en="Qwen / DashScope",
        kind="openai",
        litellm_provider="dashscope",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
        models=("qwen-plus", "qwen-max", "qwen-turbo"),
        needs_key=True,
        key_url="https://bailian.console.aliyun.com/",
        docs_url="https://docs.litellm.ai/docs/providers/dashscope",
        description="阿里云百炼 DashScope 的 OpenAI 兼容模式。",
        description_en="Alibaba Cloud Bailian DashScope, OpenAI-compatible mode.",
        group="china",
    ),
    ProviderPreset(
        id="minimax",
        label="MiniMax",
        label_en="MiniMax",
        kind="openai",
        litellm_provider="minimax",
        base_url="https://api.minimaxi.com/v1",
        default_model="MiniMax-M2.1",
        models=("MiniMax-M2.1", "MiniMax-M2", "MiniMax-Text-01"),
        needs_key=True,
        key_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        docs_url="https://docs.litellm.ai/docs/providers/minimax",
        description="MiniMax 国内站；国际站可在「高级」里改成 api.minimax.io/v1。",
        description_en=(
            "MiniMax China endpoint; switch to api.minimax.io/v1 in Advanced for the "
            "international site."
        ),
        group="china",
    ),
    ProviderPreset(
        id="baichuan",
        label="百川智能",
        label_en="Baichuan",
        kind="openai",
        litellm_provider="openai",
        base_url="https://api.baichuan-ai.com/v1",
        default_model="Baichuan4",
        models=("Baichuan4", "Baichuan4-Turbo", "Baichuan3-Turbo"),
        needs_key=True,
        key_url="https://platform.baichuan-ai.com/console/apikey",
        docs_url=None,
        description="百川 OpenAI 兼容端点（LiteLLM 无独立前缀，按 openai 协议接入）。",
        description_en=(
            "Baichuan's OpenAI-compatible endpoint (no dedicated LiteLLM prefix; routed as "
            "openai)."
        ),
        group="china",
    ),
    ProviderPreset(
        id="stepfun",
        label="阶跃星辰 StepFun",
        label_en="StepFun",
        kind="openai",
        litellm_provider="openai",
        base_url="https://api.stepfun.com/v1",
        default_model="step-2-16k",
        models=("step-2-16k", "step-1-8k"),
        needs_key=True,
        key_url="https://platform.stepfun.com/interface-key",
        docs_url=None,
        description="阶跃星辰 OpenAI 兼容端点（LiteLLM 无独立前缀，按 openai 协议接入）。",
        description_en=(
            "StepFun's OpenAI-compatible endpoint (no dedicated LiteLLM prefix; routed as "
            "openai)."
        ),
        group="china",
    ),
    ProviderPreset(
        id="yi",
        label="零一万物 Yi",
        label_en="01.AI Yi",
        kind="openai",
        litellm_provider="openai",
        base_url="https://api.lingyiwanwu.com/v1",
        default_model="yi-large",
        models=("yi-large", "yi-medium", "yi-lightning"),
        needs_key=True,
        key_url="https://platform.lingyiwanwu.com/apikeys",
        docs_url=None,
        description="零一万物 OpenAI 兼容端点（LiteLLM 无独立前缀，按 openai 协议接入）。",
        description_en=(
            "01.AI's OpenAI-compatible endpoint (no dedicated LiteLLM prefix; routed as "
            "openai)."
        ),
        group="china",
    ),
    ProviderPreset(
        id="volcengine",
        label="火山方舟 / 豆包",
        label_en="Volcengine Ark / Doubao",
        kind="openai",
        litellm_provider="volcengine",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        default_model="doubao-pro-32k",
        models=("doubao-pro-32k", "doubao-pro-128k", "doubao-lite-32k"),
        needs_key=True,
        key_url="https://console.volcengine.com/ark",
        docs_url="https://docs.litellm.ai/docs/providers/volcengine",
        description="火山引擎方舟；模型名也可填推理接入点 ID（ep-…）。",
        description_en="Volcengine Ark; the model can also be an endpoint ID (ep-…).",
        group="china",
    ),
    ProviderPreset(
        id="hunyuan",
        label="腾讯混元",
        label_en="Tencent Hunyuan",
        kind="openai",
        litellm_provider="openai",
        base_url="https://api.hunyuan.cloud.tencent.com/v1",
        default_model="hunyuan-turbos-latest",
        models=("hunyuan-turbos-latest", "hunyuan-pro", "hunyuan-lite"),
        needs_key=True,
        key_url="https://console.cloud.tencent.com/hunyuan/api-key",
        docs_url=None,
        description=(
            "腾讯混元 OpenAI 兼容端点；LiteLLM 的 tencent 前缀走 TokenHub 国际站，"
            "国内站统一按 openai 协议接入。"
        ),
        description_en=(
            "Tencent Hunyuan's OpenAI-compatible endpoint. LiteLLM's tencent prefix targets "
            "TokenHub; the China site is routed as openai."
        ),
        group="china",
    ),
    ProviderPreset(
        id="siliconflow",
        label="硅基流动 SiliconFlow",
        label_en="SiliconFlow",
        kind="openai",
        litellm_provider="openai",
        base_url="https://api.siliconflow.cn/v1",
        default_model="Qwen/Qwen3-235B-A22B",
        models=(
            "Qwen/Qwen3-235B-A22B",
            "deepseek-ai/DeepSeek-V3",
            "Qwen/Qwen2.5-72B-Instruct",
        ),
        needs_key=True,
        key_url="https://cloud.siliconflow.cn/account/ak",
        docs_url=None,
        description="硅基流动聚合平台，OpenAI 兼容端点。",
        description_en="SiliconFlow aggregation platform with an OpenAI-compatible endpoint.",
        group="china",
    ),
    # ------------------------------------------------------------------ #
    # 网关 / 海外聚合
    # ------------------------------------------------------------------ #
    ProviderPreset(
        id="openrouter",
        label="OpenRouter",
        label_en="OpenRouter",
        kind="openai",
        litellm_provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4.1-mini",
        models=("openai/gpt-4.1-mini", "anthropic/claude-sonnet-4", "google/gemini-2.5-flash"),
        needs_key=True,
        key_url="https://openrouter.ai/settings/keys",
        docs_url="https://docs.litellm.ai/docs/providers/openrouter",
        description="一个 Key 访问多家模型；模型名保留「厂商/模型」格式。",
        description_en="One key for many vendors; keep the vendor/model format in the model name.",
        group="gateway",
    ),
    ProviderPreset(
        id="groq",
        label="Groq",
        label_en="Groq",
        kind="openai",
        litellm_provider="groq",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        models=("llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"),
        needs_key=True,
        key_url="https://console.groq.com/keys",
        docs_url="https://docs.litellm.ai/docs/providers/groq",
        description="Groq 高速推理，OpenAI 兼容。",
        description_en="Groq high-speed inference, OpenAI-compatible.",
        group="gateway",
    ),
    ProviderPreset(
        id="together",
        label="Together AI",
        label_en="Together AI",
        kind="openai",
        litellm_provider="together_ai",
        base_url="https://api.together.xyz/v1",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        models=(
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "Qwen/Qwen2.5-72B-Instruct-Turbo",
        ),
        needs_key=True,
        key_url="https://api.together.xyz/settings/api-keys",
        docs_url="https://docs.litellm.ai/docs/providers/together",
        description="Together AI 开源模型托管。",
        description_en="Together AI hosted open models.",
        group="gateway",
    ),
    ProviderPreset(
        id="fireworks",
        label="Fireworks AI",
        label_en="Fireworks AI",
        kind="openai",
        litellm_provider="fireworks_ai",
        base_url="https://api.fireworks.ai/inference/v1",
        default_model="accounts/fireworks/models/llama-v3p3-70b-instruct",
        models=(
            "accounts/fireworks/models/llama-v3p3-70b-instruct",
            "accounts/fireworks/models/deepseek-v3",
        ),
        needs_key=True,
        key_url="https://fireworks.ai/account/api-keys",
        docs_url="https://docs.litellm.ai/docs/providers/fireworks_ai",
        description="Fireworks AI 推理平台。",
        description_en="Fireworks AI inference platform.",
        group="gateway",
    ),
    ProviderPreset(
        id="cerebras",
        label="Cerebras",
        label_en="Cerebras",
        kind="openai",
        litellm_provider="cerebras",
        base_url="https://api.cerebras.ai/v1",
        default_model="llama-3.3-70b",
        models=("llama-3.3-70b", "qwen-3-32b"),
        needs_key=True,
        key_url="https://cloud.cerebras.ai/",
        docs_url="https://docs.litellm.ai/docs/providers/cerebras",
        description="Cerebras 晶圆级推理。",
        description_en="Cerebras wafer-scale inference.",
        group="gateway",
    ),
    ProviderPreset(
        id="sambanova",
        label="SambaNova",
        label_en="SambaNova",
        kind="openai",
        litellm_provider="sambanova",
        base_url="https://api.sambanova.ai/v1",
        default_model="Meta-Llama-3.3-70B-Instruct",
        models=("Meta-Llama-3.3-70B-Instruct", "DeepSeek-R1"),
        needs_key=True,
        key_url="https://cloud.sambanova.ai/apis",
        docs_url="https://docs.litellm.ai/docs/providers/sambanova",
        description="SambaNova Cloud。",
        description_en="SambaNova Cloud.",
        group="gateway",
    ),
    ProviderPreset(
        id="novita",
        label="Novita AI",
        label_en="Novita AI",
        kind="openai",
        litellm_provider="novita",
        base_url="https://api.novita.ai/v3/openai",
        default_model="deepseek/deepseek-v3",
        models=("deepseek/deepseek-v3", "meta-llama/llama-3.3-70b-instruct"),
        needs_key=True,
        key_url="https://novita.ai/settings/key-management",
        docs_url="https://docs.litellm.ai/docs/providers/novita",
        description="Novita AI 聚合推理。",
        description_en="Novita AI aggregated inference.",
        group="gateway",
    ),
    ProviderPreset(
        id="nebius",
        label="Nebius AI Studio",
        label_en="Nebius AI Studio",
        kind="openai",
        litellm_provider="nebius",
        base_url="https://api.studio.nebius.com/v1",
        default_model="Qwen/Qwen3-235B-A22B",
        models=("Qwen/Qwen3-235B-A22B", "meta-llama/Llama-3.3-70B-Instruct"),
        needs_key=True,
        key_url="https://studio.nebius.com/settings/api-keys",
        docs_url="https://docs.litellm.ai/docs/providers/nebius",
        description="Nebius AI Studio。",
        description_en="Nebius AI Studio.",
        group="gateway",
    ),
    ProviderPreset(
        id="oneapi",
        label="OneAPI / NewAPI 网关",
        label_en="OneAPI / NewAPI gateway",
        kind="openai",
        litellm_provider="openai",
        base_url=None,
        default_model="gpt-4.1-mini",
        models=(),
        needs_key=True,
        key_url=None,
        docs_url=None,
        description="自建或团队内部的 OneAPI / NewAPI 聚合网关，按 OpenAI 协议接入。",
        description_en="Self-hosted OneAPI / NewAPI gateway, routed as OpenAI-compatible.",
        group="gateway",
        requires_base_url=True,
    ),
    ProviderPreset(
        id="cc-switch",
        label="CC Switch 代理",
        label_en="CC Switch proxy",
        kind="anthropic",
        litellm_provider="anthropic",
        base_url="http://127.0.0.1:15721",
        default_model="deepseek-chat",
        models=("deepseek-chat", "claude-sonnet-4", "glm-4.6"),
        needs_key=True,
        key_url=None,
        docs_url=None,
        description="CC Switch 这类本地代理，暴露 Anthropic Messages 兼容格式。",
        description_en=(
            "A local proxy such as CC Switch that exposes the Anthropic Messages format."
        ),
        group="gateway",
    ),
    # ------------------------------------------------------------------ #
    # 本地推理
    # ------------------------------------------------------------------ #
    ProviderPreset(
        id="ollama",
        label="Ollama",
        label_en="Ollama",
        kind="ollama",
        litellm_provider=None,
        base_url="http://127.0.0.1:11434",
        default_model="llama3.1",
        models=("llama3.1", "qwen3:4b", "qwen3.5:9b"),
        needs_key=False,
        key_url=None,
        docs_url="https://docs.ollama.com/",
        description="本地 Ollama 服务，无需 Key，数据不出本机。",
        description_en="Local Ollama server. No key, data never leaves this device.",
        group="local",
        local=True,
    ),
    ProviderPreset(
        id="lm-studio",
        label="LM Studio",
        label_en="LM Studio",
        kind="openai",
        litellm_provider="openai",
        base_url="http://127.0.0.1:1234/v1",
        default_model="local-model",
        models=(),
        needs_key=False,
        key_url=None,
        docs_url="https://lmstudio.ai/docs/app/api",
        description="LM Studio 本地服务器，OpenAI 兼容，无需 Key。",
        description_en="LM Studio local server, OpenAI-compatible, no key required.",
        group="local",
        local=True,
    ),
    ProviderPreset(
        id="vllm",
        label="vLLM",
        label_en="vLLM",
        kind="openai",
        litellm_provider="openai",
        base_url="http://127.0.0.1:8000/v1",
        default_model="local-model",
        models=(),
        needs_key=False,
        key_url=None,
        docs_url="https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
        description="自建 vLLM OpenAI 兼容服务器，无需 Key。",
        description_en="Self-hosted vLLM OpenAI-compatible server, no key required.",
        group="local",
        local=True,
    ),
    # ------------------------------------------------------------------ #
    # 自定义 / 演示
    # ------------------------------------------------------------------ #
    ProviderPreset(
        id="custom-openai",
        label="自定义 OpenAI 兼容",
        label_en="Custom OpenAI-compatible",
        kind="openai",
        litellm_provider="openai",
        base_url=None,
        default_model="gpt-4.1-mini",
        models=(),
        needs_key=True,
        key_url=None,
        docs_url="https://docs.litellm.ai/docs/providers/openai_compatible",
        description="任意 OpenAI 兼容端点：必须填写接口地址，模型名以服务端实际暴露为准。",
        description_en=(
            "Any OpenAI-compatible endpoint: the base URL is required; use the model name "
            "the server actually exposes."
        ),
        group="custom",
        requires_base_url=True,
        custom=True,
    ),
    ProviderPreset(
        id="mock",
        label="Mock 演示",
        label_en="Mock demo",
        kind="mock",
        litellm_provider=None,
        base_url=None,
        default_model="mock-1",
        models=("mock-1",),
        needs_key=False,
        key_url=None,
        docs_url=None,
        description="确定性回复，不联网，用来体验工具调用流程。",
        description_en="Deterministic replies with no network access; good for trying the tool loop.",
        group="demo",
        local=True,
    ),
)

PRESETS: Final[tuple[ProviderPreset, ...]] = tuple(
    sorted(_PRESETS, key=lambda item: (GROUPS.index(item.group), item.label))
)
PRESET_BY_ID: Final[dict[str, ProviderPreset]] = {item.id: item for item in PRESETS}

# 允许写入 provider 记录的 LiteLLM 前缀；未知前缀在保存时直接拒绝，避免拼错后到运行时才报错。
LITELLM_PROVIDERS: Final[frozenset[str]] = frozenset(
    {"openai", "anthropic"}
    | {item.litellm_provider for item in PRESETS if item.litellm_provider}
)


def get_preset(preset_id: str | None) -> ProviderPreset | None:
    if not preset_id:
        return None
    return PRESET_BY_ID.get(preset_id)


def list_presets() -> list[dict[str, Any]]:
    """API 视图；按分组顺序、组内按名称排序。"""
    return [preset.to_public() for preset in PRESETS]


__all__ = [
    "GROUPS",
    "LITELLM_PROVIDERS",
    "PRESETS",
    "PRESET_BY_ID",
    "ProviderPreset",
    "get_preset",
    "list_presets",
]
