import fs from "node:fs/promises";
import path from "node:path";

const DEFAULT_STATE = {
  version: 1,
  createdAt: new Date(0).toISOString(),
  tenants: [],
  partitions: [],
  agents: [],
  records: [],
  chunks: [],
  sessions: []
};

export class DiskStore {
  constructor(dataDir) {
    this.dataDir = dataDir;
    this.statePath = path.join(dataDir, "state.json");
    this.state = structuredClone(DEFAULT_STATE);
  }

  async init() {
    await fs.mkdir(this.dataDir, { recursive: true });

    try {
      const raw = await fs.readFile(this.statePath, "utf8");
      this.state = { ...structuredClone(DEFAULT_STATE), ...JSON.parse(raw) };
    } catch (error) {
      if (error.code !== "ENOENT") {
        throw error;
      }

      this.state = {
        ...structuredClone(DEFAULT_STATE),
        createdAt: new Date().toISOString()
      };
      await this.persist();
    }
  }

  read() {
    return structuredClone(this.state);
  }

  async mutate(mutator) {
    const draft = this.read();
    const result = await mutator(draft);
    this.state = draft;
    await this.persist();
    return result;
  }

  async persist() {
    await fs.writeFile(this.statePath, `${JSON.stringify(this.state, null, 2)}\n`, "utf8");
  }
}
