import http from "node:http";

import { loadConfig } from "./config.js";
import { loadEnvFile } from "./utils/env.js";
import { OpenAICompatibleEmbeddingClient, NoopEmbeddingClient } from "./providers/embeddingClient.js";
import { InfiniRerankClient, NoopRerankClient } from "./providers/rerankClient.js";
import { routeRequest } from "./router.js";
import { HubService } from "./services/hubService.js";
import { DiskStore } from "./storage/diskStore.js";

async function main() {
  loadEnvFile();
  const config = loadConfig();
  const store = new DiskStore(config.dataDir);
  await store.init();

  const embedder = config.embedding.enabled
    ? new OpenAICompatibleEmbeddingClient(config.embedding)
    : new NoopEmbeddingClient();
  const reranker = config.rerank.enabled
    ? new InfiniRerankClient(config.rerank)
    : new NoopRerankClient();
  const service = new HubService({ store, embedder, reranker, config });

  const server = http.createServer((request, response) => routeRequest(request, response, service));
  server.listen(config.port, () => {
    const health = service.health();
    console.log(
      JSON.stringify(
        {
          message: "ContextHub listening",
          port: config.port,
          dataDir: config.dataDir,
          providers: health.providers
        },
        null,
        2
      )
    );
  });
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : error);
  process.exitCode = 1;
});
