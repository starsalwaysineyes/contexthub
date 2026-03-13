import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { HubService } from "../src/services/hubService.js";
import { DiskStore } from "../src/storage/diskStore.js";

class FakeEmbedder {
  status() {
    return { enabled: true, ready: true, model: "fake" };
  }

  async embed(input) {
    return input.map((text) => {
      const normalized = String(text).toLowerCase();
      return [normalized.includes("memory") ? 1 : 0, normalized.includes("agent") ? 1 : 0];
    });
  }
}

class FakeReranker {
  status() {
    return { enabled: true, ready: true, model: "fake-rerank" };
  }

  async rank(query, documents) {
    return documents.map((document, index) => ({
      index,
      score: document.toLowerCase().includes(query.toLowerCase()) ? 1 : 0.2
    }));
  }
}

async function buildService() {
  const dataDir = await fs.mkdtemp(path.join(os.tmpdir(), "contexthub-test-"));
  const store = new DiskStore(dataDir);
  await store.init();

  return {
    dataDir,
    service: new HubService({
      store,
      embedder: new FakeEmbedder(),
      reranker: new FakeReranker(),
      config: {
        retrieval: {
          defaultLimit: 5,
          candidateLimit: 10,
          rerankTopN: 5,
          lexicalWeight: 0.45,
          vectorWeight: 0.35,
          manualWeight: 0.15,
          recencyWeight: 0.05
        },
        rerank: {
          enabled: true
        }
      },
      now: () => "2026-03-13T12:00:00.000Z"
    })
  };
}

test("stores records and returns relevant query results", async () => {
  const { service, dataDir } = await buildService();

  try {
    const tenant = await service.createTenant({ slug: "demo", name: "Demo" });
    await service.createPartition({ tenantId: tenant.id, key: "memory", name: "Memory" });
    await service.createRecord({
      tenantId: tenant.id,
      partitionKey: "memory",
      type: "memory",
      title: "Memory retrieval",
      text: "ContextHub should help every agent reuse memory safely.",
      importance: 5,
      pinned: true
    });

    const result = await service.query({
      tenantId: tenant.id,
      query: "memory for agent",
      partitions: ["memory"],
      rerank: true
    });

    assert.equal(result.items.length, 1);
    assert.equal(result.items[0].title, "Memory retrieval");
    assert.equal(result.retrieval.usedEmbeddings, true);
  } finally {
    await fs.rm(dataDir, { recursive: true, force: true });
  }
});

test("session commit can materialize memory entries", async () => {
  const { service, dataDir } = await buildService();

  try {
    const tenant = await service.createTenant({ slug: "demo", name: "Demo" });
    const partition = await service.createPartition({
      tenantId: tenant.id,
      key: "project-openclaw",
      name: "Project OpenClaw"
    });
    const agent = await service.registerAgent({ tenantId: tenant.id, name: "OpenClaw" });

    const commit = await service.commitSession({
      tenantId: tenant.id,
      partitionKey: partition.key,
      agentId: agent.id,
      summary: "Agreed on multi-agent context backend.",
      messages: [{ role: "user", content: "Build a context backend." }],
      memoryEntries: [
        {
          title: "Architecture direction",
          text: "Prefer manual curation first and controlled cross-partition retrieval.",
          importance: 4
        }
      ]
    });

    assert.equal(commit.createdMemories.length, 1);

    const result = await service.query({
      tenantId: tenant.id,
      query: "cross-partition retrieval",
      partitions: [partition.key]
    });

    assert.equal(result.items.length, 1);
    assert.equal(result.items[0].title, "Architecture direction");
  } finally {
    await fs.rm(dataDir, { recursive: true, force: true });
  }
});
