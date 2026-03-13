import { createId } from "../utils/id.js";
import { splitIntoChunks, recencyScore, clamp } from "../utils/text.js";
import { cosineSimilarity, lexicalScore, manualScore } from "../retrieval/scorers.js";

function requireValue(value, fieldName) {
  if (value === undefined || value === null || value === "") {
    throw new Error(`Missing required field: ${fieldName}`);
  }
}

function normalizeKey(value) {
  return String(value).trim().toLowerCase();
}

function textForChunk(record, chunkText) {
  return [record.title, record.manualSummary, chunkText].filter(Boolean).join("\n\n");
}

export class HubService {
  constructor({ store, embedder, reranker, config, now = () => new Date().toISOString() }) {
    this.store = store;
    this.embedder = embedder;
    this.reranker = reranker;
    this.config = config;
    this.now = now;
  }

  health() {
    const state = this.store.read();

    return {
      ok: true,
      counts: {
        tenants: state.tenants.length,
        partitions: state.partitions.length,
        agents: state.agents.length,
        records: state.records.length,
        chunks: state.chunks.length,
        sessions: state.sessions.length
      },
      providers: {
        embedding: this.embedder.status(),
        rerank: this.reranker.status()
      }
    };
  }

  async createTenant(input) {
    requireValue(input.slug, "slug");
    requireValue(input.name, "name");

    const slug = normalizeKey(input.slug);

    return this.store.mutate((state) => {
      const existing = state.tenants.find((tenant) => tenant.slug === slug);

      if (existing) {
        return existing;
      }

      const tenant = {
        id: createId("tenant"),
        slug,
        name: String(input.name).trim(),
        description: input.description ? String(input.description).trim() : "",
        createdAt: this.now()
      };

      state.tenants.push(tenant);
      return tenant;
    });
  }

  async createPartition(input) {
    requireValue(input.tenantId, "tenantId");
    requireValue(input.key, "key");
    requireValue(input.name, "name");

    const key = normalizeKey(input.key);

    return this.store.mutate((state) => {
      this.#assertTenant(state, input.tenantId);

      const existing = state.partitions.find(
        (partition) => partition.tenantId === input.tenantId && partition.key === key
      );

      if (existing) {
        return existing;
      }

      const partition = {
        id: createId("partition"),
        tenantId: input.tenantId,
        key,
        name: String(input.name).trim(),
        kind: input.kind ? normalizeKey(input.kind) : "context",
        description: input.description ? String(input.description).trim() : "",
        allowCrossQueryFrom: Array.isArray(input.allowCrossQueryFrom)
          ? input.allowCrossQueryFrom.map(normalizeKey)
          : [],
        createdAt: this.now()
      };

      state.partitions.push(partition);
      return partition;
    });
  }

  async registerAgent(input) {
    requireValue(input.tenantId, "tenantId");
    requireValue(input.name, "name");

    return this.store.mutate((state) => {
      this.#assertTenant(state, input.tenantId);

      const agent = {
        id: createId("agent"),
        tenantId: input.tenantId,
        name: String(input.name).trim(),
        kind: input.kind ? normalizeKey(input.kind) : "generic",
        metadata: input.metadata ?? {},
        createdAt: this.now()
      };

      state.agents.push(agent);
      return agent;
    });
  }

  async createRecord(input) {
    requireValue(input.tenantId, "tenantId");
    requireValue(input.partitionKey, "partitionKey");
    requireValue(input.type, "type");
    requireValue(input.title, "title");
    requireValue(input.text, "text");

    const partitionKey = normalizeKey(input.partitionKey);
    const idempotencyKey = input.idempotencyKey ? normalizeKey(input.idempotencyKey) : null;
    const now = this.now();

    const chunks = splitIntoChunks(input.text);
    const embeddings = await this.#embedChunks(chunks);

    return this.store.mutate((state) => {
      this.#assertTenant(state, input.tenantId);
      this.#assertPartition(state, input.tenantId, partitionKey);

      const existing = idempotencyKey
        ? state.records.find(
            (record) => record.tenantId === input.tenantId && record.idempotencyKey === idempotencyKey
          )
        : null;

      if (existing) {
        return existing;
      }

      const record = {
        id: createId("record"),
        tenantId: input.tenantId,
        partitionKey,
        type: normalizeKey(input.type),
        title: String(input.title).trim(),
        text: String(input.text).trim(),
        source: input.source ?? null,
        tags: Array.isArray(input.tags) ? input.tags.map((tag) => String(tag).trim()).filter(Boolean) : [],
        metadata: input.metadata ?? {},
        manualSummary: input.manualSummary ? String(input.manualSummary).trim() : "",
        importance: clamp(Number(input.importance) || 0, 0, 5),
        pinned: Boolean(input.pinned),
        idempotencyKey,
        createdAt: now,
        updatedAt: now,
        chunkIds: []
      };

      const chunkObjects = chunks.map((text, index) => ({
        id: createId("chunk"),
        recordId: record.id,
        tenantId: record.tenantId,
        partitionKey: record.partitionKey,
        index,
        text,
        vector: Array.isArray(embeddings?.[index]) ? embeddings[index] : null,
        createdAt: now
      }));

      record.chunkIds = chunkObjects.map((chunk) => chunk.id);
      state.records.push(record);
      state.chunks.push(...chunkObjects);
      return record;
    });
  }

  async commitSession(input) {
    requireValue(input.tenantId, "tenantId");
    requireValue(input.partitionKey, "partitionKey");

    const partitionKey = normalizeKey(input.partitionKey);
    const now = this.now();
    const sessionId = input.sessionId ? String(input.sessionId) : createId("session");
    const messages = Array.isArray(input.messages) ? input.messages : [];
    const summary = input.summary ? String(input.summary).trim() : "";
    const memoryEntries = Array.isArray(input.memoryEntries) ? input.memoryEntries : [];

    const session = await this.store.mutate((state) => {
      this.#assertTenant(state, input.tenantId);
      this.#assertPartition(state, input.tenantId, partitionKey);

      const payload = {
        id: sessionId,
        tenantId: input.tenantId,
        partitionKey,
        agentId: input.agentId ?? null,
        summary,
        metadata: input.metadata ?? {},
        messages,
        createdAt: now
      };

      state.sessions.push(payload);
      return payload;
    });

    const createdMemories = [];

    for (const entry of memoryEntries) {
      const memory = await this.createRecord({
        tenantId: input.tenantId,
        partitionKey,
        type: entry.type ?? "memory",
        title: entry.title,
        text: entry.text,
        manualSummary: entry.manualSummary ?? summary,
        source: {
          sessionId,
          kind: "session-commit"
        },
        tags: entry.tags,
        metadata: {
          ...(entry.metadata ?? {}),
          sessionId
        },
        importance: entry.importance ?? 3,
        pinned: Boolean(entry.pinned),
        idempotencyKey: entry.idempotencyKey
      });

      createdMemories.push(memory);
    }

    return { session, createdMemories };
  }

  async query(input) {
    requireValue(input.tenantId, "tenantId");
    requireValue(input.query, "query");

    const state = this.store.read();
    this.#assertTenant(state, input.tenantId);

    const allowedPartitionSet = new Set(
      (Array.isArray(input.partitions) && input.partitions.length > 0
        ? input.partitions
        : state.partitions.filter((partition) => partition.tenantId === input.tenantId).map((partition) => partition.key)
      ).map(normalizeKey)
    );

    const allowedTypes = new Set(
      (Array.isArray(input.types) ? input.types : []).map(normalizeKey)
    );

    const relevantRecords = state.records.filter((record) => {
      if (record.tenantId !== input.tenantId) {
        return false;
      }

      if (!allowedPartitionSet.has(record.partitionKey)) {
        return false;
      }

      if (allowedTypes.size > 0 && !allowedTypes.has(record.type)) {
        return false;
      }

      return true;
    });

    const chunkMap = new Map(state.chunks.map((chunk) => [chunk.id, chunk]));
    const candidateChunks = relevantRecords.flatMap((record) =>
      record.chunkIds.map((chunkId) => ({ record, chunk: chunkMap.get(chunkId) })).filter((item) => item.chunk)
    );

    const queryVectorList = await this.#embedChunks([String(input.query)]);
    const queryVector = Array.isArray(queryVectorList?.[0]) ? queryVectorList[0] : null;
    const weights = this.config.retrieval;
    const now = Date.now();

    const scored = candidateChunks
      .map(({ record, chunk }) => {
        const lexical = lexicalScore(input.query, textForChunk(record, chunk.text));
        const vector = queryVector && Array.isArray(chunk.vector) ? cosineSimilarity(queryVector, chunk.vector) : 0;
        const manual = manualScore(record);
        const recency = recencyScore(record.updatedAt ?? record.createdAt, now);
        const baseScore =
          lexical * weights.lexicalWeight +
          vector * weights.vectorWeight +
          manual * weights.manualWeight +
          recency * weights.recencyWeight;

        return {
          record,
          chunk,
          lexical,
          vector,
          manual,
          recency,
          score: baseScore,
          rerank: null
        };
      })
      .filter((item) => item.score > 0)
      .sort((left, right) => right.score - left.score)
      .slice(0, weights.candidateLimit);

    const wantsRerank = Boolean(input.rerank ?? this.config.rerank.enabled);

    if (wantsRerank && scored.length > 0) {
      const rerankWindow = scored.slice(0, this.config.retrieval.rerankTopN);
      const rerankResults = await this.#safeRerank(
        input.query,
        rerankWindow.map(({ record, chunk }) => textForChunk(record, chunk.text))
      );

      if (rerankResults) {
        const rerankScoreMap = new Map(rerankResults.map((item) => [item.index, item.score]));

        rerankWindow.forEach((item, index) => {
          item.rerank = rerankScoreMap.get(index) ?? 0;
          item.score = item.score * 0.65 + (item.rerank ?? 0) * 0.35;
        });
      }
    }

    const results = scored
      .sort((left, right) => right.score - left.score)
      .slice(0, Number(input.limit) || weights.defaultLimit)
      .map((item) => ({
        recordId: item.record.id,
        chunkId: item.chunk.id,
        title: item.record.title,
        type: item.record.type,
        partitionKey: item.record.partitionKey,
        score: Number(item.score.toFixed(6)),
        snippet: item.chunk.text,
        manualSummary: item.record.manualSummary,
        source: item.record.source,
        tags: item.record.tags,
        createdAt: item.record.createdAt,
        trace: {
          lexical: Number(item.lexical.toFixed(6)),
          vector: Number(item.vector.toFixed(6)),
          manual: Number(item.manual.toFixed(6)),
          recency: Number(item.recency.toFixed(6)),
          rerank: item.rerank === null ? null : Number(item.rerank.toFixed(6))
        }
      }));

    return {
      items: results,
      retrieval: {
        candidateCount: candidateChunks.length,
        scoredCount: scored.length,
        usedEmbeddings: Boolean(queryVector),
        usedRerank: wantsRerank && results.some((item) => item.trace.rerank !== null)
      }
    };
  }

  #assertTenant(state, tenantId) {
    const tenant = state.tenants.find((item) => item.id === tenantId);

    if (!tenant) {
      throw new Error(`Unknown tenant: ${tenantId}`);
    }
  }

  #assertPartition(state, tenantId, partitionKey) {
    const partition = state.partitions.find(
      (item) => item.tenantId === tenantId && item.key === partitionKey
    );

    if (!partition) {
      throw new Error(`Unknown partition: ${partitionKey}`);
    }
  }

  async #embedChunks(chunks) {
    if (!Array.isArray(chunks) || chunks.length === 0) {
      return [];
    }

    try {
      return await this.embedder.embed(chunks);
    } catch (error) {
      return null;
    }
  }

  async #safeRerank(query, documents) {
    try {
      return await this.reranker.rank(query, documents);
    } catch (error) {
      return null;
    }
  }
}
