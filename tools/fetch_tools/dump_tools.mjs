#!/usr/bin/env node
/**
 * dump_tools.mjs
 * 从 OpenClaw bundle 提取所有工具的完整 JSON Schema（含 description）
 * 输出到 stdout（JSON 数组），可重定向到文件
 *
 * 用法:
 *   node dump_tools.mjs                          # 输出到 stdout
 *   node dump_tools.mjs > openclaw_all_tools.json
 */

import { readFileSync, readdirSync } from 'fs';
import { createRequire } from 'module';
import path from 'path';
import { fileURLToPath } from 'url';

const require = createRequire(import.meta.url);

// ── 加载 TypeBox ────────────────────────────────────────────────────────────
let Type;
try {
  ({ Type } = require('@sinclair/typebox'));
} catch {
  const candidates = [
    '/opt/homebrew/lib/node_modules/openclaw/node_modules/@sinclair/typebox/build/cjs/index.js',
    path.join(process.env.HOME, 'node_modules/@sinclair/typebox/build/cjs/index.js'),
  ];
  for (const p of candidates) {
    try { ({ Type } = require(p)); break; } catch {}
  }
}
if (!Type) { console.error('ERROR: @sinclair/typebox not found'); process.exit(1); }

// ── Bundle 路径 ─────────────────────────────────────────────────────────────
const OPENCLAW_DIST = '/opt/homebrew/lib/node_modules/openclaw/dist';
const PI_CODING_TOOLS = path.join(
  process.env.HOME, 'node_modules/@mariozechner/pi-coding-agent/dist/core/tools'
);

function findBundle(prefix) {
  const f = readdirSync(OPENCLAW_DIST).find(n => n.startsWith(prefix) && n.endsWith('.js'));
  return f ? readFileSync(path.join(OPENCLAW_DIST, f), 'utf8') : null;
}

const piSrc    = findBundle('pi-embedded');
const replySrc = findBundle('reply');
if (!piSrc) { console.error('ERROR: pi-embedded bundle not found'); process.exit(1); }

// ── TypeBox eval helper ─────────────────────────────────────────────────────
function evalTypeboxExpr(expr) {
  const helpers = `
    const optionalStringEnum = (values, opts={}) =>
      Type.Optional(Type.Union(values.map(v => Type.Literal(v)), opts));
    const stringEnum = (values, opts={}) =>
      Type.Union(values.map(v => Type.Literal(v)), opts);
    const EXTRACT_MODES = ["markdown", "text"];
    const CRON_ACTIONS = ["status","list","add","update","remove","run","runs","wake"];
    const CRON_WAKE_MODES = ["now","next-heartbeat"];
    const CRON_RUN_MODES = ["due","force"];
    const REMINDER_CONTEXT_MESSAGES_MAX = 10;
  `;
  try {
    return new Function('Type', helpers + `return ${expr}`)(Type);
  } catch(e) {
    return null;
  }
}

function extractSchema(src, startStr) {
  const pos = src.indexOf(startStr);
  if (pos === -1) return null;
  const chunk = src.slice(pos);
  let depth = 0, i = 0;
  while (i < chunk.length && chunk[i] !== '(') i++;
  for (; i < chunk.length; i++) {
    if (chunk[i] === '(') depth++;
    else if (chunk[i] === ')') { depth--; if (depth === 0) { i++; break; } }
  }
  return evalTypeboxExpr(chunk.slice(0, i));
}

// ── 从 pi-coding-agent 提取 read / write / edit ────────────────────────────
function extractCodingAgentTool(file, varName) {
  try {
    const src = readFileSync(path.join(PI_CODING_TOOLS, file), 'utf8');
    // tool description 在工具对象里，可能用双引号或反引号（模板字符串）
    const toolDescM = src.match(/name:\s*"[^"]+",\s*\n\s*label:[^,]+,\s*\n\s*description:\s*["`]([^"`]+)["`]/s);
    let description = toolDescM ? toolDescM[1].replace(/\s+/g, ' ').trim() : file.replace('.js', '');
    // 展开常量（截断相关）
    const truncateSrc = (() => { try { return readFileSync(path.join(PI_CODING_TOOLS, 'truncate.js'), 'utf8'); } catch { return ''; } })();
    const maxLines = (truncateSrc.match(/DEFAULT_MAX_LINES\s*=\s*(\d+)/) || [])[1] || '2000';
    const maxBytes = (truncateSrc.match(/DEFAULT_MAX_BYTES\s*=\s*(\d+)/) || [])[1] || '50';
    description = description
      .replace(/\$\{DEFAULT_MAX_LINES\}/g, maxLines)
      .replace(/\$\{DEFAULT_MAX_BYTES\s*\/\s*1024\}/g, maxBytes)
      .replace(/\$\{[^}]+\}/g, ''); // 其余模板变量清除
    return { description, schema: extractSchema(src, `${varName} = Type.Object(`) };
  } catch { return null; }
}

// ── 从 bundle 提取工具（pi-embedded 或 reply） ─────────────────────────────
function extractBundleTool(src, varName, descHint) {
  const schema = extractSchema(src, `${varName} = Type.Object(`);
  if (!schema) return null;

  // 优先从工具对象定义里找 description（name: "xxx" 附近）
  let description = descHint;

  // 找工具名（从 varName 推断 tool name）
  const schemaPos = src.indexOf(`${varName} = Type.Object(`);
  // 在 schema 定义前后找 name:"xxx" + description:"yyy" 模式
  const searchWindow = src.slice(Math.max(0, schemaPos - 2000), schemaPos + 500);
  const toolDefM = searchWindow.match(/name:\s*"([^"]+)",\s*\n?\s*(?:label:[^\n]+\n\s*)?description:\s*"([^"]{20,500})"/);
  if (toolDefM) description = toolDefM[2];

  return { description, schema };
}

// ── image: 内联在 createImageTool 里 ──────────────────────────────────────
function extractImage(src) {
  const pos = src.indexOf('name: "image"');
  if (pos === -1) return null;
  const chunk = src.slice(pos, pos + 3000);

  // description 就在 name: "image" 后面
  const dm = chunk.match(/name:\s*"image",\s*\n?\s*(?:label:[^\n]+\n\s*)?description:\s*"([^"]{20,400})"/);
  const description = dm ? dm[1] : 'Analyze one or more images with a vision model.';

  const paramPos = chunk.indexOf('parameters: Type.Object(');
  if (paramPos === -1) return null;
  const schema = extractSchema(chunk.slice(paramPos + 'parameters: '.length), 'Type.Object(');
  if (!schema) return null;
  return { description, schema };
}

// ── memory: 在 reply bundle 或 memory plugin ───────────────────────────────
function extractMemoryTools(src) {
  const result = {};

  // memory_search
  const msPos = src.indexOf('name: "memory_search"');
  if (msPos > -1) {
    const chunk = src.slice(msPos, msPos + 3000);
    const paramPos = chunk.indexOf('parameters: Type.Object(');
    if (paramPos > -1) {
      const schema = extractSchema(chunk.slice(paramPos + 'parameters: '.length), 'Type.Object(');
      if (schema) {
        const dm = chunk.match(/description:\s*"([^"]{20,400})"/);
        result.memory_search = { description: dm ? dm[1] : 'Semantically search memory files.', schema };
      }
    }
  }

  // memory_get
  const mgPos = src.indexOf('name: "memory_get"');
  if (mgPos > -1) {
    const chunk = src.slice(mgPos, mgPos + 3000);
    const paramPos = chunk.indexOf('parameters: Type.Object(');
    if (paramPos > -1) {
      const schema = extractSchema(chunk.slice(paramPos + 'parameters: '.length), 'Type.Object(');
      if (schema) {
        const dm = chunk.match(/description:\s*"([^"]{20,300})"/);
        result.memory_get = { description: dm ? dm[1] : 'Safe snippet read from memory files.', schema };
      }
    }
  }

  return result;
}

// ── 提取 sessions_spawn（含 optionalStringEnum） ───────────────────────────
function extractSessionsSpawn() {
  // 先拿到 SESSIONS_SPAWN_RUNTIMES 的值
  const rrMatch = piSrc.match(/SESSIONS_SPAWN_RUNTIMES\s*=\s*(\[[^\]]+\])/);
  const runtimes = rrMatch ? JSON.parse(rrMatch[1]) : ['subagent', 'acp'];

  const smMatch = piSrc.match(/SESSIONS_SPAWN_SANDBOX_MODES\s*=\s*(\[[^\]]+\])/);
  const sandboxModes = smMatch ? JSON.parse(smMatch[1]) : ['inherit', 'require'];

  const modesMatch = piSrc.match(/SESSIONS_SPAWN_MODES\s*=\s*(\[[^\]]+\])/);
  const modes = modesMatch ? JSON.parse(modesMatch[1]) : ['run', 'session'];

  const cleanupMatch = piSrc.match(/SESSIONS_SPAWN_CLEANUP\s*=\s*(\[[^\]]+\])/);
  const cleanup = cleanupMatch ? JSON.parse(cleanupMatch[1]) : ['delete', 'keep'];

  const streamToMatch = piSrc.match(/SESSIONS_SPAWN_STREAM_TO\s*=\s*(\[[^\]]+\])/);
  const streamTo = streamToMatch ? JSON.parse(streamToMatch[1]) : ['parent'];

  // 手动构建（避免 optionalStringEnum 依赖问题）
  const schema = Type.Object({
    task: Type.String(),
    label: Type.Optional(Type.String({ maxLength: 64, minLength: 1 })),
    runtime: Type.Optional(Type.Union(runtimes.map(v => Type.Literal(v)))),
    agentId: Type.Optional(Type.String()),
    resumeSessionId: Type.Optional(Type.String({
      description: 'Resume an existing agent session by its ID (e.g. a Codex session UUID from ~/.codex/sessions/). Requires runtime="acp". The agent replays conversation history via session/load instead of starting fresh.'
    })),
    model: Type.Optional(Type.String()),
    thinking: Type.Optional(Type.String()),
    cwd: Type.Optional(Type.String()),
    runTimeoutSeconds: Type.Optional(Type.Number({ minimum: 0 })),
    timeoutSeconds: Type.Optional(Type.Number({ minimum: 0 })),
    thread: Type.Optional(Type.Boolean()),
    mode: Type.Optional(Type.Union(modes.map(v => Type.Literal(v)))),
    cleanup: Type.Optional(Type.Union(cleanup.map(v => Type.Literal(v)))),
    sandbox: Type.Optional(Type.Union(sandboxModes.map(v => Type.Literal(v)))),
    streamTo: Type.Optional(Type.Union(streamTo.map(v => Type.Literal(v)))),
  });

  return {
    description: 'Spawn an isolated session (runtime="subagent" or runtime="acp"). mode="run" is one-shot and mode="session" is persistent/thread-bound. Subagents inherit the parent workspace directory automatically.',
    schema
  };
}

// ── 提取 web_search ────────────────────────────────────────────────────────
function extractWebSearch() {
  if (!replySrc) return null;
  // 直接手动构建（createWebSearchSchema 依赖运行时 provider config）
  const schema = Type.Object({
    query: Type.String({ description: 'Search query string.' }),
    count: Type.Optional(Type.Number({ description: 'Number of results to return (1-10).', minimum: 1, maximum: 10 })),
    country: Type.Optional(Type.String({ description: "2-letter country code for region-specific results (e.g., 'DE', 'US', 'ALL'). Default: 'US'." })),
    language: Type.Optional(Type.String({ description: "ISO 639-1 language code for results (e.g., 'en', 'de', 'fr')." })),
    freshness: Type.Optional(Type.String({ description: "Filter by time: 'day' (24h), 'week', 'month', or 'year'." })),
    date_after: Type.Optional(Type.String({ description: 'Only results published after this date (YYYY-MM-DD).' })),
    date_before: Type.Optional(Type.String({ description: 'Only results published before this date (YYYY-MM-DD).' })),
    search_lang: Type.Optional(Type.String({ description: "Brave language code for search results (e.g., 'en', 'de', 'en-gb')." })),
    ui_lang: Type.Optional(Type.String({ description: "Locale code for UI elements (e.g., 'en-US', 'de-DE'). Must include region subtag." })),
  });
  return {
    description: 'Search the web using Brave Search API. Supports region-specific and localized search via country and language parameters. Returns titles, URLs, and snippets for fast research.',
    schema
  };
}

// ── 主流程 ─────────────────────────────────────────────────────────────────
const TOOL_DEFS = [
  // pi-coding-agent
  { name: 'read',  fn: () => extractCodingAgentTool('read.js',  'readSchema') },
  { name: 'write', fn: () => extractCodingAgentTool('write.js', 'writeSchema') },
  { name: 'edit',  fn: () => extractCodingAgentTool('edit.js',  'editSchema') },
  // pi-embedded
  { name: 'exec',            fn: () => extractBundleTool(piSrc,    'execSchema',             'Execute shell commands with background continuation.') },
  { name: 'process',         fn: () => extractBundleTool(piSrc,    'processSchema',           'Manage running exec sessions: list, poll, log, write, send-keys, submit, paste, kill.') },
  { name: 'sessions_list',   fn: () => extractBundleTool(piSrc,    'SessionsListToolSchema',  'List sessions with optional filters and last messages.') },
  { name: 'sessions_history',fn: () => extractBundleTool(piSrc,    'SessionsHistoryToolSchema','Fetch message history for a session.') },
  { name: 'sessions_send',   fn: () => extractBundleTool(piSrc,    'SessionsSendToolSchema',  'Send a message into another session.') },
  { name: 'sessions_spawn',  fn: () => extractSessionsSpawn() },
  { name: 'subagents',       fn: () => extractBundleTool(piSrc,    'SubagentsToolSchema',     'List, kill, or steer spawned sub-agents for this requester session.') },
  { name: 'session_status',  fn: () => extractBundleTool(piSrc,    'SessionStatusToolSchema', 'Show a /status-equivalent session status card.') },
  { name: 'cron',            fn: () => extractBundleTool(piSrc,    'CronToolSchema',          'Manage Gateway cron jobs (status/list/add/update/remove/run/runs) and send wake events.') },
  // reply bundle — memory tools have named schema vars
  { name: 'memory_search',   fn: () => replySrc ? extractBundleTool(replySrc, 'MemorySearchSchema', 'Mandatory recall step: semantically search MEMORY.md + memory/*.md (and optional session transcripts) before answering questions about prior work, decisions, dates, people, preferences, or todos; returns top snippets with path + lines.') : null },
  { name: 'memory_get',      fn: () => replySrc ? extractBundleTool(replySrc, 'MemoryGetSchema',    'Safe snippet read from MEMORY.md or memory/*.md with optional from/lines; use after memory_search to pull only the needed lines and keep context small.') : null },
  { name: 'web_fetch',       fn: () => replySrc ? extractBundleTool(replySrc, 'WebFetchSchema', 'Fetch and extract readable content from a URL.') : null },
  { name: 'web_search',      fn: () => extractWebSearch() },
  { name: 'image',           fn: () => replySrc ? extractImage(replySrc) : null },
];

// memory tools (inline in reply bundle, not a named schema var) — 已合并到 TOOL_DEFS，移除旧的 extractMemoryTools 调用

const output = [];
for (const { name, fn } of TOOL_DEFS) {
  const result = fn();
  if (!result) { process.stderr.write(`⚠️  ${name}: failed\n`); continue; }
  output.push({ type: 'function', function: { name, description: result.description, parameters: result.schema } });
  process.stderr.write(`✅ ${name}\n`);
}

process.stderr.write(`\nTotal: ${output.length} tools\n`);
process.stdout.write(JSON.stringify(output, null, 2) + '\n');
