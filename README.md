# Imago

Programmable text-to-image pipeline powered by FLUX on Apple Silicon.

Imago converts natural language intents into images through an LLM-powered prompt expansion pipeline and the FLUX generative model. It serves as the visual output layer for the [OpenClaw](https://github.com/anthropics/openclaw) agent ecosystem while supporting standalone batch workflows.

## Features

- **Prompt Factory** — short intent in, detailed FLUX prompt out (via Claude / Bailian / Qwen)
- **Style Templates** — cinematic, product, editorial, finance_editorial, tech_illustration, social_cover
- **img2img** — transform reference images with text guidance and strength control
- **Batch Generation** — variable expansion (cartesian product) for bulk creation
- **Persistent Task Queue** — SQLite-backed, crash-resilient, auto-retry
- **Webhook Callbacks** — real-time notifications with optional base64 images
- **OpenClaw Plugin** — `imago_generate`, `imago_img2img`, `imago_styles` tools for AI agents
- **Feishu Integration** — automatic image upload and delivery

## Quick Start

```bash
# Install
pip install -e .

# Configure (copy and edit)
cp .env.example .env

# Run
imago
```

The server starts on `http://0.0.0.0:8420` by default.

## API

### Text-to-Image

```bash
curl -X POST http://localhost:8420/generate \
  -H "Content-Type: application/json" \
  -d '{"intent": "a cat in a spacesuit", "style": "cinematic"}'
```

### Image-to-Image

```bash
curl -X POST http://localhost:8420/generate \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "cyberpunk neon style",
    "image_url": "/path/to/reference.png",
    "image_strength": 0.4
  }'
```

`image_strength` controls how much of the reference image to preserve (0.0 = ignore, 1.0 = maximum preservation, default 0.4).

### Check Task Status

```bash
curl http://localhost:8420/tasks/{task_id}
```

### List Styles

```bash
curl http://localhost:8420/styles
```

## Configuration

All settings are configurable via environment variables (prefix `IMAGO_`). See [.env.example](.env.example) for the full list.

Key settings:

| Variable | Default | Description |
|---|---|---|
| `IMAGO_MODEL` | schnell | FLUX model variant (schnell / dev) |
| `IMAGO_STEPS` | 4 | Inference steps |
| `IMAGO_LLM_PROVIDER` | bailian | Prompt expansion LLM (bailian / claude / qwen) |
| `IMAGO_OUTPUT_DIR` | ./output | Generated image output directory |

## Development

```bash
# Install dev dependencies
pip install -e . && pip install pytest pytest-asyncio pytest-httpx

# Run tests
pytest
```

## Architecture

```
POST /generate → TaskQueue (SQLite) → Worker → PromptFactory → FLUX → OutputManager
                                                                ↑
                                                          img2img: image_url
                                                          + image_strength
```

## License

Private.
