import fs from "node:fs";
import path from "node:path";
import process from "node:process";

function loadSingleEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return;
  }

  const content = fs.readFileSync(filePath, "utf8");
  const lines = content.split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();

    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separatorIndex = trimmed.indexOf("=");

    if (separatorIndex === -1) {
      continue;
    }

    const key = trimmed.slice(0, separatorIndex).trim();
    const rawValue = trimmed.slice(separatorIndex + 1).trim();
    const value = rawValue.replace(/^['"]|['"]$/g, "");

    if (!(key in process.env)) {
      process.env[key] = value;
    }
  }
}

export function loadEnvFile() {
  const cwd = process.cwd();
  const explicitPath = process.env.CONTEXT_HUB_ENV_FILE;

  if (explicitPath) {
    loadSingleEnvFile(path.resolve(explicitPath));
    return;
  }

  const candidates = [".env.local", ".env"].map((name) => path.join(cwd, name));

  for (const candidate of candidates) {
    loadSingleEnvFile(candidate);
  }
}
