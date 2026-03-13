import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const ROOT = process.cwd();
const SKIP_DIRS = new Set([".git", "node_modules", "var"]);
const SKIP_FILES = new Set(["package-lock.json"]);
const PATTERNS = [
  { name: "OpenAI-style key", regex: /\bsk-[A-Za-z0-9_-]{12,}\b/g },
  { name: "GitHub token", regex: /\bgh[pousr]_[A-Za-z0-9_]{12,}\b/g },
  { name: "Google API key", regex: /\bAIza[0-9A-Za-z\-_]{20,}\b/g },
  { name: "Bearer token", regex: /Bearer\s+[A-Za-z0-9._-]{20,}/g }
];

async function walk(dirPath, files = []) {
  const entries = await fs.readdir(dirPath, { withFileTypes: true });

  for (const entry of entries) {
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) {
        continue;
      }

      await walk(path.join(dirPath, entry.name), files);
      continue;
    }

    if (SKIP_FILES.has(entry.name)) {
      continue;
    }

    files.push(path.join(dirPath, entry.name));
  }

  return files;
}

function lineNumberAt(content, index) {
  return content.slice(0, index).split(/\r?\n/).length;
}

async function main() {
  const files = await walk(ROOT);
  const violations = [];

  for (const filePath of files) {
    const relativePath = path.relative(ROOT, filePath);
    const content = await fs.readFile(filePath, "utf8");

    for (const pattern of PATTERNS) {
      const matches = content.matchAll(pattern.regex);

      for (const match of matches) {
        const line = lineNumberAt(content, match.index ?? 0);
        violations.push({
          path: relativePath,
          line,
          kind: pattern.name,
          value: match[0].slice(0, 16) + "..."
        });
      }
    }
  }

  if (violations.length === 0) {
    console.log("Secret scan passed.");
    return;
  }

  console.error("Potential secrets detected:");
  for (const violation of violations) {
    console.error(`- ${violation.path}:${violation.line} ${violation.kind} ${violation.value}`);
  }

  process.exitCode = 1;
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : error);
  process.exitCode = 1;
});
