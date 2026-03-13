export class ContextHubClient {
  constructor({ baseUrl, token = null, headers = {} }) {
    if (!baseUrl) {
      throw new Error("Missing baseUrl");
    }

    this.baseUrl = String(baseUrl).replace(/\/$/, "");
    this.token = token;
    this.headers = headers;
  }

  async health() {
    return this.#request("GET", "/health");
  }

  async createTenant(payload) {
    return this.#request("POST", "/v1/tenants", payload);
  }

  async createPartition(payload) {
    return this.#request("POST", "/v1/partitions", payload);
  }

  async registerAgent(payload) {
    return this.#request("POST", "/v1/agents", payload);
  }

  async createRecord(payload) {
    return this.#request("POST", "/v1/records", payload);
  }

  async query(payload) {
    return this.#request("POST", "/v1/query", payload);
  }

  async commitSession(payload) {
    return this.#request("POST", "/v1/sessions/commit", payload);
  }

  async #request(method, pathname, body) {
    const headers = {
      Accept: "application/json",
      ...this.headers
    };

    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`;
    }

    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(`${this.baseUrl}${pathname}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body)
    });

    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;

    if (!response.ok) {
      const detail = payload?.error ?? response.statusText;
      throw new Error(`ContextHub request failed (${method} ${pathname}): ${detail}`);
    }

    return payload;
  }
}
