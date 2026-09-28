import { chmod } from "node:fs/promises";
import { resolve } from "node:path";
import { build } from "esbuild";

const packageRoot = resolve(import.meta.dirname, "..");

// MCP 服务器入口：src/mcp/server.ts -> dist/mcp/server.js
const serverOutputPath = resolve(packageRoot, "dist", "mcp", "server.js");
// CLI 后台分析入口：src/cli.ts -> dist/cli.js
const cliOutputPath = resolve(packageRoot, "dist", "cli.js");

const common = {
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node24",
  legalComments: "none",
  define: { __REPO_ROOT__: JSON.stringify(packageRoot) },
  // 打包 CJS 依赖（imapflow/mailparser/nodemailer 均为 CJS）到 ESM 产物时，
  // esbuild 的 __require shim 会因 ESM 作用域内 require 未定义而抛错，
  // 用 banner 定义真正的 createRequire 兜底。
  banner: {
    js: `import { createRequire as __zcodeCreateRequire } from "node:module";
const require = __zcodeCreateRequire(import.meta.url);`,
  },
};

await build({
  ...common,
  entryPoints: [resolve(packageRoot, "src", "mcp", "server.ts")],
  outfile: serverOutputPath,
});

await build({
  ...common,
  entryPoints: [resolve(packageRoot, "src", "cli.ts")],
  outfile: cliOutputPath,
});

await chmod(serverOutputPath, 0o755);
await chmod(cliOutputPath, 0o755);

console.log("build done: dist/mcp/server.js, dist/cli.js");
