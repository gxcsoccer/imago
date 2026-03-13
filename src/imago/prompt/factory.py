from __future__ import annotations

import logging

import anthropic
import httpx

from imago.config import Settings
from imago.prompt.styles import StyleRegistry, StyleTemplate

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a prompt engineer for FLUX, a state-of-the-art text-to-image model.

Your task: expand a short user intent into a detailed, high-quality FLUX image prompt.

Rules:
- Output ONLY the final prompt text in English, nothing else
- Keep it under 200 words
- Be specific about composition, lighting, color palette, mood, and style
- Use descriptive noun phrases separated by commas
- Do not include negative prompts or meta-instructions
- Do not wrap in quotes
"""

IMG2IMG_SYSTEM_PROMPT = """\
You are a prompt engineer for FLUX img2img (image-to-image style transfer).

The user has a reference image and wants to transform it into a new style. Your task: \
write a prompt that describes the TARGET STYLE the image should be transformed into.

Rules:
- Output ONLY the final prompt text in English, nothing else
- Keep it under 150 words
- Focus on the TARGET STYLE and aesthetic, NOT the scene content (the scene comes from the reference image)
- Describe the art style, rendering technique, color palette, lighting mood, and texture
- Use descriptive noun phrases separated by commas
- Do not describe what's in the image — only describe HOW it should look
- Do not include negative prompts or meta-instructions
- Do not wrap in quotes

Examples:
- Intent "anime style" → "japanese anime art style, cel shading, clean lineart, vibrant flat colors, large expressive eyes, smooth skin rendering, soft ambient lighting, anime key visual quality, studio ghibli-inspired palette"
- Intent "oil painting" → "classical oil painting on canvas, thick impasto brushstrokes, rich warm color palette, chiaroscuro lighting, renaissance composition, visible paint texture, museum quality fine art"
- Intent "cyberpunk" → "cyberpunk aesthetic, neon-lit atmosphere, teal and magenta color grading, holographic overlays, rain-slicked reflections, futuristic UI elements, blade runner inspired, cinematic sci-fi mood"
"""


def _build_user_message(intent: str, style: StyleTemplate | None) -> str:
    parts = [f"User intent: {intent}"]
    if style:
        parts.append(f"\nStyle: {style.name} — {style.description}")
        parts.append(f"Style prefix (include at start): {style.prefix}")
        parts.append(f"Style suffix (include at end): {style.suffix}")
        if style.example_expansions:
            ex = style.example_expansions[0]
            parts.append(f"\nExample for reference:")
            parts.append(f"  Intent: {ex['intent']}")
            parts.append(f"  Expanded: {ex['expanded']}")
    return "\n".join(parts)


def _build_img2img_user_message(intent: str) -> str:
    return f"Transform the reference image into this style: {intent}"


class PromptFactory:
    def __init__(self, settings: Settings, style_registry: StyleRegistry) -> None:
        self.settings = settings
        self.style_registry = style_registry

    async def expand(
        self,
        intent: str,
        style_name: str | None = None,
        is_img2img: bool = False,
    ) -> str:
        style = self.style_registry.get(style_name) if style_name else None

        # If no LLM is configured, fall back to simple template-based expansion
        provider = self.settings.llm_provider
        if provider == "claude" and not self.settings.anthropic_api_key:
            logger.warning("No ANTHROPIC_API_KEY set, using template-only expansion")
            return self._template_fallback(intent, style)
        if provider == "bailian" and not self.settings.bailian_api_key:
            logger.warning("No BAILIAN_API_KEY set, using template-only expansion")
            return self._template_fallback(intent, style)

        # For img2img, use the style-focused system prompt and skip style templates
        if is_img2img:
            system_prompt = IMG2IMG_SYSTEM_PROMPT
            user_msg = _build_img2img_user_message(intent)
        else:
            system_prompt = SYSTEM_PROMPT
            user_msg = _build_user_message(intent, style)

        if provider == "bailian":
            return await self._expand_openai_compat(
                user_msg,
                base_url=self.settings.bailian_base_url,
                api_key=self.settings.bailian_api_key,
                model=self.settings.bailian_model,
                label="Bailian",
                system_prompt=system_prompt,
            )
        if provider == "qwen":
            return await self._expand_openai_compat(
                user_msg,
                base_url=self.settings.ollama_base_url,
                api_key="ollama",
                model=self.settings.qwen_model,
                label="Qwen",
                system_prompt=system_prompt,
            )
        return await self._expand_claude(user_msg, system_prompt=system_prompt)

    def _template_fallback(self, intent: str, style: StyleTemplate | None) -> str:
        if style:
            return f"{style.prefix}, {intent}, {style.suffix}"
        return intent

    async def _expand_claude(
        self, user_msg: str, system_prompt: str = SYSTEM_PROMPT
    ) -> str:
        client = anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        response = await client.messages.create(
            model=self.settings.claude_model,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = response.content[0].text.strip()
        logger.info("Claude expanded prompt (%d chars)", len(text))
        return text

    async def _expand_openai_compat(
        self,
        user_msg: str,
        base_url: str,
        api_key: str,
        model: str,
        label: str,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> str:
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=180, proxy=None, trust_env=False) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 512,
                    "temperature": 0.7,
                    "extra_body": {"enable_thinking": False},
                },
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            logger.info("%s expanded prompt (%d chars)", label, len(text))
            return text
