以 **Imago** 为名，spec 如下：

---

## Imago · Project Spec

### Vision

一条从"文字意图"到"图像输出"的可编程流水线，以 Mac mini M4 Pro 为本地生成引擎，既能作为 OpenClaw 生态的视觉输出层，也能独立运行批量创作任务。

---

### 核心模块---

### 模块说明

**Prompt Factory** — 核心差异点。用户只需输入简短意图，LLM（本地 Qwen 或 Claude API）负责扩写成高质量 FLUX prompt，并注入风格前缀（如 `cinematic`, `product photography`, `tech illustration`）。支持变量模板批量展开。

**Generation Engine** — 基于 `mflux` 的 FastAPI wrapper，暴露 HTTP 接口。参数：`prompt / model / steps / size / seed / count`。内置任务队列、并发限制（避免 GPU 过热）、失败自动重试。

**Output Manager** — 生成完成后自动处理命名（`{date}-{subject}-{seed}.png`）、写入元数据 sidecar JSON、按规则分发到目标。

---

### 接口设计

```
POST /generate
{
  "intent": "HIMS 财报飞书封面",        // 自然语言 or 完整 prompt
  "style": "finance editorial",         // 可选，覆盖默认风格
  "count": 3,
  "size": "1024x1024",
  "output": ["local", "feishu"],        // 分发目标

  // img2img（可选，不传则为纯文生图）
  "image_url": "/path/to/ref.png",      // 参考图：本地路径或 HTTP URL
  "image_strength": 0.4                 // 参考图影响力 0.0-1.0，默认 0.4
}

→ 返回 task_id，异步 webhook 回调
```

**img2img 说明**

当 `image_url` 非空时进入图生图模式。参考图经 VAE 编码到 latent space 后与噪声混合，`image_strength` 控制保留程度：
- `0.2-0.3`：大幅改变，仅保留构图轮廓
- `0.4-0.5`：平衡混合（默认）
- `0.6-0.8`：高保留，仅微调色彩/风格

`image_url` 支持本地路径和 HTTP(S) URL（服务端自动下载）。与 `style`、`variables` 等参数可组合使用。

**OpenClaw 集成**

插件注册两个生成工具：
- `imago_generate` — 文生图，Agent 传自然语言 intent
- `imago_img2img` — 图生图，Agent 传参考图路径/URL + 变换意图，支持飞书图片自动下载与回传

---

### 里程碑

| 阶段 | 目标 | 交付物 |
|------|------|------|
| M1 | 跑通单张生成 | mflux wrapper + FastAPI |
| M2 | Prompt Factory | LLM 扩写 + 风格模板库 |
| M3 | 批量 + 队列 | 任务队列 + 进度追踪 |
| M4 | OpenClaw 集成 | Coordinator 自动触发 + 飞书推送 |
| M5 | img2img | 图生图支持 + OpenClaw imago_img2img tool |
