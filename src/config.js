import path from "node:path";
import process from "node:process";

function toNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toBoolean(value, fallback = false) {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }

  return ["1", "true", "yes", "on"].includes(String(value).toLowerCase());
}

export function loadConfig(env = process.env) {
  const rootDir = process.cwd();
  const port = toNumber(env.CONTEXT_HUB_PORT ?? env.PORT, 4040);

  return {
    port,
    dataDir: path.resolve(env.CONTEXT_HUB_DATA_DIR ?? path.join(rootDir, "var", "data")),
    retrieval: {
      defaultLimit: toNumber(env.CONTEXT_HUB_DEFAULT_LIMIT, 8),
      candidateLimit: toNumber(env.CONTEXT_HUB_CANDIDATE_LIMIT, 40),
      rerankTopN: toNumber(env.CONTEXT_HUB_RERANK_TOP_N, 8),
      lexicalWeight: toNumber(env.CONTEXT_HUB_LEXICAL_WEIGHT, 0.45),
      vectorWeight: toNumber(env.CONTEXT_HUB_VECTOR_WEIGHT, 0.35),
      manualWeight: toNumber(env.CONTEXT_HUB_MANUAL_WEIGHT, 0.15),
      recencyWeight: toNumber(env.CONTEXT_HUB_RECENCY_WEIGHT, 0.05)
    },
    embedding: {
      enabled: toBoolean(env.CONTEXT_HUB_ENABLE_EMBEDDINGS, true),
      baseUrl: (env.CONTEXT_HUB_EMBEDDING_BASE_URL ?? "https://cloud.infini-ai.com/maas/v1").replace(/\/$/, ""),
      apiKey: env.CONTEXT_HUB_EMBEDDING_API_KEY ?? "",
      model: env.CONTEXT_HUB_EMBEDDING_MODEL ?? "bge-m3"
    },
    rerank: {
      enabled: toBoolean(env.CONTEXT_HUB_ENABLE_RERANK, false),
      baseUrl: (env.CONTEXT_HUB_RERANK_BASE_URL ?? "https://cloud.infini-ai.com/maas/v1").replace(/\/$/, ""),
      apiKey: env.CONTEXT_HUB_RERANK_API_KEY ?? "",
      model: env.CONTEXT_HUB_RERANK_MODEL ?? "bge-reranker-v2-m3"
    }
  };
}
