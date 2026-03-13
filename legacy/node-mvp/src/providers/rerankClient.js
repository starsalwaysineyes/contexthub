export class NoopRerankClient {
  constructor() {
    this.enabled = false;
  }

  status() {
    return { enabled: false, ready: false, model: null };
  }

  async rank() {
    return null;
  }
}

export class InfiniRerankClient {
  constructor({ baseUrl, apiKey, model }) {
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
    this.model = model;
    this.enabled = Boolean(apiKey);
  }

  status() {
    return {
      enabled: true,
      ready: this.enabled,
      model: this.model,
      baseUrl: this.baseUrl
    };
  }

  async rank(query, documents) {
    if (!this.enabled || !query || !Array.isArray(documents) || documents.length === 0) {
      return null;
    }

    const response = await fetch(`${this.baseUrl}/rerank`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.apiKey}`
      },
      body: JSON.stringify({
        model: this.model,
        query,
        documents
      })
    });

    if (!response.ok) {
      throw new Error(`Rerank request failed: ${response.status}`);
    }

    const payload = await response.json();
    const results = Array.isArray(payload.results) ? payload.results : [];

    return results.map((item) => ({
      index: item.index,
      score: item.relevance_score ?? item.score ?? 0
    }));
  }
}
