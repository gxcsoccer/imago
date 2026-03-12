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
    registerStylesTool(api, config);
    registerTaskStatusTool(api, config);
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
