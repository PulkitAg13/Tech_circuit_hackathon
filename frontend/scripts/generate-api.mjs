import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, "..");
const backendDir = path.resolve(frontendDir, "../backend");
const openapiJsonRelative = "./openapi.json";
const schemaOutRelative = "./src/api/schema.d.ts";

console.log("Generating OpenAPI schema from FastAPI backend...");

const extraPath = "C:\\Users\\HP PAVILION\\AppData\\Local\\Programs\\Python\\Python310\\Scripts";
const env = { ...process.env, PATH: `${extraPath};${process.env.PATH}` };

// Export from backend to frontend/openapi.json
const commands = [
  `uv run python -c "import json; from canongate.api.app import app; json.dump(app.openapi(), open('../frontend/openapi.json', 'w', encoding='utf-8'), indent=2)"`,
  `python -c "import json; from canongate.api.app import app; json.dump(app.openapi(), open('../frontend/openapi.json', 'w', encoding='utf-8'), indent=2)"`,
  `py -3 -c "import json; from canongate.api.app import app; json.dump(app.openapi(), open('../frontend/openapi.json', 'w', encoding='utf-8'), indent=2)"`,
];

let generated = false;
for (const cmd of commands) {
  try {
    execSync(cmd, { cwd: backendDir, env, stdio: "inherit" });
    generated = true;
    break;
  } catch {
    // try next
  }
}

if (!generated) {
  console.error("Failed to dump OpenAPI schema from FastAPI.");
  process.exit(1);
}

console.log(`Wrote OpenAPI JSON to ${openapiJsonRelative}`);
console.log("Generating TypeScript types with openapi-typescript...");

const npxCmd = process.platform === "win32" ? "npx.cmd" : "npx";
execSync(`${npxCmd} openapi-typescript ${openapiJsonRelative} -o ${schemaOutRelative}`, {
  cwd: frontendDir,
  env,
  stdio: "inherit",
});

console.log(`TypeScript schema successfully generated at ${schemaOutRelative}`);
