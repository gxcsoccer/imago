# Imago

基于 FLUX + Apple Silicon 的可编程文生图流水线。

Imago 将自然语言意图通过 LLM 扩写为高质量 FLUX prompt，在本地 Mac mini M4 Pro 上生成图片。既是 OpenClaw Agent 生态的视觉输出层，也可独立运行批量创作任务。

## 功能特性

- **Prompt Factory** — 输入简短意图，LLM 自动扩写为详细 FLUX prompt（支持 Claude / 百炼 / Qwen）
- **风格模板** — cinematic、product、editorial、finance_editorial、tech_illustration、social_cover
- **图生图 (img2img)** — 基于参考图 + 文字引导生成新图，可控制保留强度
- **批量生成** — 变量模板笛卡尔积展开，一次请求生成多张变体
- **持久化任务队列** — SQLite 存储，崩溃恢复，自动重试
- **Webhook 回调** — 任务完成/失败实时通知，可附带 base64 图片
- **OpenClaw 插件** — `imago_generate`、`imago_img2img`、`imago_styles` 三个 Agent 工具
- **飞书集成** — 自动上传图片并发送给用户

## 快速开始

```bash
# 安装
pip install -e .

# 配置（复制后编辑）
cp .env.example .env

# 启动
imago
```

服务默认监听 `http://0.0.0.0:8420`。

## API 接口

### 文生图

```bash
curl -X POST http://localhost:8420/generate \
  -H "Content-Type: application/json" \
  -d '{"intent": "穿宇航服的猫", "style": "cinematic"}'
```

### 图生图

```bash
curl -X POST http://localhost:8420/generate \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "赛博朋克霓虹风格",
    "image_url": "/path/to/reference.png",
    "image_strength": 0.4
  }'
```

`image_strength` 控制参考图的保留程度：
- `0.2-0.3` — 大幅改变，仅保留构图轮廓
- `0.4-0.5` — 平衡混合（默认）
- `0.6-0.8` — 高保留，仅微调色彩/风格

`image_url` 支持本地路径和 HTTP(S) URL（服务端自动下载）。

### 查询任务状态

```bash
curl http://localhost:8420/tasks/{task_id}
```

### 查看风格列表

```bash
curl http://localhost:8420/styles
```

## 配置

所有配置通过环境变量设置（前缀 `IMAGO_`），完整列表见 [.env.example](.env.example)。

主要配置项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `IMAGO_MODEL` | schnell | FLUX 模型（schnell / dev） |
| `IMAGO_STEPS` | 4 | 推理步数 |
| `IMAGO_LLM_PROVIDER` | bailian | prompt 扩写 LLM（bailian / claude / qwen） |
| `IMAGO_OUTPUT_DIR` | ./output | 图片输出目录 |

## 开发

```bash
# 安装开发依赖
pip install -e . && pip install pytest pytest-asyncio pytest-httpx

# 运行测试
pytest
```

## 架构

```
POST /generate → TaskQueue (SQLite) → Worker → PromptFactory → FLUX → OutputManager
                                                                 ↑
                                                           img2img: image_url
                                                           + image_strength
```

## 许可

私有项目。
