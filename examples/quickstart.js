import { ContextHubClient } from "../src/client/contextHubClient.js";

const client = new ContextHubClient({
  baseUrl: process.env.CONTEXT_HUB_BASE_URL ?? "http://127.0.0.1:4040"
});

async function main() {
  const tenant = await client.createTenant({
    slug: "openclaw-china",
    name: "OpenClaw China"
  });

  await client.createPartition({
    tenantId: tenant.id,
    key: "project-openclaw",
    name: "Project OpenClaw",
    kind: "project"
  });

  await client.createRecord({
    tenantId: tenant.id,
    partitionKey: "project-openclaw",
    type: "memory",
    title: "ContextHub direction",
    text: "Single instance multi-tenant, manual curation first, optional rerank.",
    importance: 4,
    pinned: true,
    idempotencyKey: "project-openclaw:direction:v1"
  });

  const result = await client.query({
    tenantId: tenant.id,
    query: "manual curation and multi-tenant",
    partitions: ["project-openclaw"],
    rerank: false,
    limit: 3
  });

  console.log(JSON.stringify(result, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : error);
  process.exitCode = 1;
});
