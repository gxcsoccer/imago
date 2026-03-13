/**
 * Imago — OpenClaw Plugin
 *
 * Registers image generation tools so OpenClaw agents can generate
 * images from natural language intents via the local Imago API.
 * After generation, uploads image to Feishu and sends it directly.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";

interface ImagoConfig {
  baseUrl: string;
}

interface FeishuConfig {
  appId: string;
  appSecret: string;
  domain: string;
}

function resolveConfig(raw: Record<string, unknown> | undefined): ImagoConfig {
  return {
    baseUrl: (raw?.baseUrl as string) ?? "http://127.0.0.1:8420",
  };
}

function resolveFeishuConfig(apiConfig: Record<string, unknown> | undefined): FeishuConfig | null {
  const channels = apiConfig?.channels as Record<string, unknown> | undefined;
  const feishu = channels?.feishu as Record<string, unknown> | undefined;
  if (!feishu?.appId || !feishu?.appSecret) return null;
  return {
    appId: feishu.appId as string,
    appSecret: feishu.appSecret as string,
    domain: (feishu.domain as string) === "lark" ? "lark" : "feishu",
  };
}

// ── Feishu API helpers ──────────────────────────────────────

async function getFeishuToken(cfg: FeishuConfig): Promise<string> {
  const baseUrl = cfg.domain === "lark"
    ? "https://open.larksuite.com"
    : "https://open.feishu.cn";
  const resp = await fetch(`${baseUrl}/open-apis/auth/v3/tenant_access_token/internal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ app_id: cfg.appId, app_secret: cfg.appSecret }),
  });
  const data = (await resp.json()) as { tenant_access_token: string };
  return data.tenant_access_token;
}

async function uploadImageToFeishu(
  cfg: FeishuConfig,
  token: string,
  imagePath: string,
): Promise<string> {
  const baseUrl = cfg.domain === "lark"
    ? "https://open.larksuite.com"
    : "https://open.feishu.cn";
  const imageBuffer = fs.readFileSync(imagePath);
  const blob = new Blob([imageBuffer], { type: "image/png" });
  const form = new FormData();
  form.append("image_type", "message");
  form.append("image", blob, path.basename(imagePath));

  const resp = await fetch(`${baseUrl}/open-apis/im/v1/images`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const data = (await resp.json()) as { data: { image_key: string } };
  return data.data.image_key;
}

async function sendFeishuImage(
  cfg: FeishuConfig,
  token: string,
  receiveId: string,
  imageKey: string,
  receiveIdType: string = "open_id",
): Promise<boolean> {
  const baseUrl = cfg.domain === "lark"
    ? "https://open.larksuite.com"
    : "https://open.feishu.cn";
  const resp = await fetch(
    `${baseUrl}/open-apis/im/v1/messages?receive_id_type=${receiveIdType}`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        receive_id: receiveId,
        msg_type: "image",
        content: JSON.stringify({ image_key: imageKey }),
      }),
    },
  );
  return resp.ok;
}

// ── Plugin Entry ────────────────────────────────────────────

export default {
  id: "imago",
  name: "Imago",
  description: "Text-to-image generation pipeline",
  version: "0.1.0",

  register(api: OpenClawPluginApi) {
    const config = resolveConfig(api.pluginConfig);
    const feishuCfg = resolveFeishuConfig(api.config as Record<string, unknown>);
    api.logger.info(`Imago: connecting to ${config.baseUrl}`);
    if (feishuCfg) {
      api.logger.info("Imago: Feishu image delivery enabled");
    }

    registerGenerateTool(api, config, feishuCfg);
    registerImg2ImgTool(api, config, feishuCfg);
    registerStylesTool(api, config);
    registerTaskStatusTool(api, config);

    // Inject img2img guidance into agent system prompt
    api.registerHook("before_prompt_build", () => ({
      appendSystemContext: [
        "## Imago 图片生成工具选择规则（必须遵守）",
        "重要：当消息上下文中存在 MediaPath（即用户发送了图片），你必须使用 imago_img2img 工具，而不是 imago_generate。",
        "- imago_img2img：用户发了图片 + 要求变换/修改/增强 → 必须用此工具。image_url 填 MediaPath 的值，intent 填用户的变换描述。",
        "- imago_generate：用户没有发图片，只用文字描述想要的图片 → 用此工具。",
        "",
        "### image_strength 选择指南（重要）",
        "image_strength 控制保留程度（0=完全忽略原图，1=完全保留原图）：",
        "- 风格迁移（如转动漫/油画/水彩/赛博朋克）→ 用 0.25~0.35，大幅改变渲染风格",
        "- 色调/氛围微调（如暖色调/复古感）→ 用 0.6~0.7，保留大部分原图",
        "- 平衡混合 → 用 0.4~0.5",
        "- 不要传 style 参数给 img2img，服务端会自动生成适合风格迁移的 prompt",
      ].join("\n"),
    }), { name: "imago-prompt-guidance" });
  },
};

// ── imago_generate ──────────────────────────────────────────

function registerGenerateTool(
  api: OpenClawPluginApi,
  config: ImagoConfig,
  feishuCfg: FeishuConfig | null,
) {
  api.registerTool(
    (ctx) => ({
      name: "imago_generate",
      description:
        "Generate images from a text description using the local Imago service " +
        "(FLUX on Apple Silicon). This tool waits for generation to complete and " +
        "sends the image directly to the user in Feishu. " +
        "Supports style templates " +
        "(cinematic, product, editorial, finance_editorial, tech_illustration, social_cover) " +
        "and batch generation via count parameter. May take 1-3 minutes.",
      parameters: {
        type: "object" as const,
        properties: {
          intent: {
            type: "string",
            description:
              "Natural language description of the desired image. Can be Chinese or English. " +
              "Will be expanded into a detailed FLUX prompt by LLM.",
          },
          style: {
            type: "string",
            enum: [
              "cinematic",
              "product",
              "editorial",
              "finance_editorial",
              "tech_illustration",
              "social_cover",
            ],
            description: "Optional style template to apply",
          },
          count: {
            type: "number",
            description: "Number of images to generate (default: 1, max: 20)",
          },
          raw_prompt: {
            type: "boolean",
            description:
              "If true, use intent as-is without LLM expansion (for pre-crafted prompts)",
          },
          width: { type: "number", description: "Image width in pixels (default: 1024)" },
          height: { type: "number", description: "Image height in pixels (default: 1024)" },
          seed: { type: "number", description: "Random seed for reproducibility" },
        },
        required: ["intent"],
      },
      execute: async (_toolCallId: string, args: Record<string, unknown>) => {
        const body: Record<string, unknown> = { intent: args.intent };
        if (args.style) body.style = args.style;
        if (args.count) body.count = args.count;
        if (args.raw_prompt) body.raw_prompt = args.raw_prompt;
        if (args.width) body.width = args.width;
        if (args.height) body.height = args.height;
        if (args.seed) body.seed = args.seed;

        // Step 1: Submit task
        let resp: Response;
        try {
          resp = await fetch(`${config.baseUrl}/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
        } catch (err) {
          return `Imago 服务连接失败: ${err}. 请确认 Imago 服务正在运行。`;
        }

        if (!resp.ok) {
          const text = await resp.text();
          return `Imago error (${resp.status}): ${text}`;
        }

        const data = (await resp.json()) as { task_id: string };
        const taskId = data.task_id;

        // Step 2: Poll until complete (max 5 minutes)
        const maxWait = 300_000;
        const pollInterval = 10_000;
        const start = Date.now();

        while (Date.now() - start < maxWait) {
          await new Promise((r) => setTimeout(r, pollInterval));

          let statusResp: Response;
          try {
            statusResp = await fetch(`${config.baseUrl}/tasks/${taskId}`);
          } catch {
            continue;
          }

          if (!statusResp.ok) continue;

          const task = (await statusResp.json()) as {
            task_id: string;
            status: string;
            images: { path: string; seed: number; prompt: string }[];
            progress: { completed?: number; total?: number };
            error?: string;
          };

          if (task.status === "completed" && task.images.length > 0) {
            // Step 3: Upload and send images via Feishu
            const senderId = ctx?.requesterSenderId;
            let feishuSent = false;

            if (feishuCfg && senderId) {
              try {
                const token = await getFeishuToken(feishuCfg);
                for (const img of task.images) {
                  if (fs.existsSync(img.path)) {
                    const imageKey = await uploadImageToFeishu(feishuCfg, token, img.path);
                    await sendFeishuImage(feishuCfg, token, senderId, imageKey);
                    api.logger.info(`Imago: sent image to Feishu (${img.path} → ${imageKey})`);
                  }
                }
                feishuSent = true;
              } catch (err) {
                api.logger.warn(`Imago: Feishu image delivery failed: ${err}`);
              }
            }

            if (feishuSent) {
              return `图片已生成并发送到飞书 (共 ${task.images.length} 张，seed: ${task.images.map((i) => i.seed).join(", ")})`;
            }
            // Fallback: return file paths
            const lines = [`图片已生成完成 (共 ${task.images.length} 张):`];
            for (const img of task.images) {
              lines.push(`  - ${img.path} (seed: ${img.seed})`);
            }
            return lines.join("\n");
          }

          if (task.status === "failed") {
            return `图片生成失败: ${task.error ?? "unknown error"}`;
          }
        }

        return `图片生成超时 (task: ${taskId})，可以稍后用 imago_task_status 查询。`;
      },
    }),
    { names: ["imago_generate"] },
  );
}

// ── imago_img2img ──────────────────────────────────────────

function registerImg2ImgTool(
  api: OpenClawPluginApi,
  config: ImagoConfig,
  feishuCfg: FeishuConfig | null,
) {
  api.registerTool(
    (ctx) => ({
      name: "imago_img2img",
      description:
        "Generate a new image based on a reference image (image-to-image). " +
        "Use this when the user sends an image and wants to transform it " +
        "(change style, enhance, reimagine), or to iterate on a previously " +
        "generated image. When the user sends an image in the conversation, " +
        "use the MediaPath from the context as the image_url. " +
        "Supports style templates and strength control. May take 1-3 minutes.",
      parameters: {
        type: "object" as const,
        properties: {
          intent: {
            type: "string",
            description:
              "Description of desired changes or target style. Can be Chinese or English. " +
              "Will be expanded into a detailed FLUX prompt by LLM.",
          },
          image_url: {
            type: "string",
            description:
              "Reference image source: use MediaPath from context when user sends an image, " +
              "a local file path from a previous imago_generate result, " +
              "or an HTTP/HTTPS URL.",
          },
          image_strength: {
            type: "number",
            description:
              "How much of the reference image to preserve (0.0=ignore completely, 1.0=keep exactly). " +
              "For style transfer (anime, oil painting, watercolor): use 0.25-0.35 (low preservation = big change). " +
              "For balanced blend: use 0.4-0.5. " +
              "For subtle color/mood tweaks: use 0.6-0.7 (high preservation). " +
              "Default: 0.35. The server auto-boosts inference steps for quality.",
          },
          style: {
            type: "string",
            enum: [
              "cinematic",
              "product",
              "editorial",
              "finance_editorial",
              "tech_illustration",
              "social_cover",
            ],
            description: "Optional style template to apply",
          },
          width: { type: "number", description: "Image width in pixels (default: 1024)" },
          height: { type: "number", description: "Image height in pixels (default: 1024)" },
          seed: { type: "number", description: "Random seed for reproducibility" },
        },
        required: ["intent", "image_url"],
      },
      execute: async (_toolCallId: string, args: Record<string, unknown>) => {
        // If image_url is a Feishu message resource, download it first
        let imageUrl = args.image_url as string;
        if (feishuCfg && imageUrl.includes("/im/v1/messages/")) {
          try {
            const token = await getFeishuToken(feishuCfg);
            const baseUrl = feishuCfg.domain === "lark"
              ? "https://open.larksuite.com"
              : "https://open.feishu.cn";
            const resp = await fetch(`${baseUrl}${imageUrl.startsWith("/") ? "" : "/"}${imageUrl}`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (resp.ok) {
              const buffer = Buffer.from(await resp.arrayBuffer());
              const tmpDir = path.join(config.baseUrl.replace(/^https?:\/\/[^/]+/, ""), "_ref");
              const tmpPath = path.join("/tmp", `imago-ref-${Date.now()}.png`);
              fs.writeFileSync(tmpPath, buffer);
              imageUrl = tmpPath;
              api.logger.info(`Imago: downloaded Feishu image to ${tmpPath}`);
            }
          } catch (err) {
            api.logger.warn(`Imago: failed to download Feishu image: ${err}`);
          }
        }

        const body: Record<string, unknown> = {
          intent: args.intent,
          image_url: imageUrl,
        };
        if (args.image_strength !== undefined) body.image_strength = args.image_strength;
        if (args.style) body.style = args.style;
        if (args.width) body.width = args.width;
        if (args.height) body.height = args.height;
        if (args.seed) body.seed = args.seed;

        // Submit task
        let resp: Response;
        try {
          resp = await fetch(`${config.baseUrl}/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
        } catch (err) {
          return `Imago 服务连接失败: ${err}. 请确认 Imago 服务正在运行。`;
        }

        if (!resp.ok) {
          const text = await resp.text();
          return `Imago error (${resp.status}): ${text}`;
        }

        const data = (await resp.json()) as { task_id: string };
        const taskId = data.task_id;

        // Poll until complete (max 5 minutes)
        const maxWait = 300_000;
        const pollInterval = 10_000;
        const start = Date.now();

        while (Date.now() - start < maxWait) {
          await new Promise((r) => setTimeout(r, pollInterval));

          let statusResp: Response;
          try {
            statusResp = await fetch(`${config.baseUrl}/tasks/${taskId}`);
          } catch {
            continue;
          }

          if (!statusResp.ok) continue;

          const task = (await statusResp.json()) as {
            task_id: string;
            status: string;
            images: { path: string; seed: number; prompt: string }[];
            progress: { completed?: number; total?: number };
            error?: string;
          };

          if (task.status === "completed" && task.images.length > 0) {
            const senderId = ctx?.requesterSenderId;
            let feishuSent = false;

            if (feishuCfg && senderId) {
              try {
                const token = await getFeishuToken(feishuCfg);
                for (const img of task.images) {
                  if (fs.existsSync(img.path)) {
                    const imageKey = await uploadImageToFeishu(feishuCfg, token, img.path);
                    await sendFeishuImage(feishuCfg, token, senderId, imageKey);
                    api.logger.info(`Imago: sent img2img result to Feishu (${img.path} → ${imageKey})`);
                  }
                }
                feishuSent = true;
              } catch (err) {
                api.logger.warn(`Imago: Feishu image delivery failed: ${err}`);
              }
            }

            if (feishuSent) {
              return `图片已基于参考图生成并发送到飞书 (共 ${task.images.length} 张，seed: ${task.images.map((i) => i.seed).join(", ")})`;
            }
            const lines = [`图片已基于参考图生成完成 (共 ${task.images.length} 张):`];
            for (const img of task.images) {
              lines.push(`  - ${img.path} (seed: ${img.seed})`);
            }
            return lines.join("\n");
          }

          if (task.status === "failed") {
            return `图片生成失败: ${task.error ?? "unknown error"}`;
          }
        }

        return `图片生成超时 (task: ${taskId})，可以稍后用 imago_task_status 查询。`;
      },
    }),
    { names: ["imago_img2img"] },
  );
}

// ── imago_task_status ───────────────────────────────────────

function registerTaskStatusTool(api: OpenClawPluginApi, config: ImagoConfig) {
  api.registerTool(
    () => ({
      name: "imago_task_status",
      description:
        "Check the status of an Imago image generation task. " +
        "Returns status (pending/running/completed/failed), progress, and image paths.",
      parameters: {
        type: "object" as const,
        properties: {
          task_id: {
            type: "string",
            description: "Task ID returned by imago_generate",
          },
        },
        required: ["task_id"],
      },
      execute: async (_toolCallId: string, args: Record<string, unknown>) => {
        const taskId = args.task_id as string;

        let resp: Response;
        try {
          resp = await fetch(`${config.baseUrl}/tasks/${taskId}`);
        } catch (err) {
          return `Imago 服务连接失败: ${err}`;
        }

        if (!resp.ok) {
          if (resp.status === 404) return `Task ${taskId} not found.`;
          const text = await resp.text();
          return `Imago error (${resp.status}): ${text}`;
        }

        const task = (await resp.json()) as {
          task_id: string;
          status: string;
          images: { path: string; seed: number; prompt: string }[];
          progress: { completed?: number; total?: number };
          error?: string;
        };

        const lines = [`Task: ${task.task_id}`, `Status: ${task.status}`];

        if (task.progress?.total) {
          lines.push(`Progress: ${task.progress.completed ?? 0}/${task.progress.total}`);
        }

        if (task.status === "completed" && task.images.length > 0) {
          lines.push(`\nGenerated ${task.images.length} image(s):`);
          for (const img of task.images) {
            lines.push(`  - ${img.path} (seed: ${img.seed})`);
          }
        }

        if (task.status === "failed" && task.error) {
          lines.push(`Error: ${task.error}`);
        }

        return lines.join("\n");
      },
    }),
    { names: ["imago_task_status"] },
  );
}

// ── imago_styles ────────────────────────────────────────────

function registerStylesTool(api: OpenClawPluginApi, config: ImagoConfig) {
  api.registerTool(
    () => ({
      name: "imago_styles",
      description: "List available Imago style templates for image generation.",
      parameters: {
        type: "object" as const,
        properties: {},
      },
      execute: async () => {
        let resp: Response;
        try {
          resp = await fetch(`${config.baseUrl}/styles`);
        } catch (err) {
          return `Imago 服务连接失败: ${err}`;
        }
        if (!resp.ok) return `Imago error (${resp.status})`;

        const styles = (await resp.json()) as { name: string; description: string }[];
        return styles.map((s) => `- **${s.name}**: ${s.description}`).join("\n");
      },
    }),
    { names: ["imago_styles"] },
  );
}
