export class NoopEmbeddingClient {
  constructor() {
    this.enabled = false;
  }

  status() {
    return { enabled: false, ready: false, model: null };
  }

  async embed() {
    return null;
  }
}

export class OpenAICompatibleEmbeddingClient {
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

  async embed(input) {
    if (!this.enabled || !Array.isArray(input) || input.length === 0) {
      return null;
    }

    const response = await fetch(`${this.baseUrl}/embeddings`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.apiKey}`
      },
      body: JSON.stringify({
        model: this.model,
        input
      })
    });

    if (!response.ok) {
      throw new Error(`Embedding request failed: ${response.status}`);
    }

    const payload = await response.json();
    return Array.isArray(payload.data)
      ? payload.data.map((item) => item.embedding ?? null)
      : null;
  }
}
