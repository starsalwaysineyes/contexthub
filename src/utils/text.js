const TOKEN_SPLIT = /[^\p{L}\p{N}_-]+/u;

export function tokenize(text) {
  return String(text)
    .toLowerCase()
    .split(TOKEN_SPLIT)
    .map((token) => token.trim())
    .filter(Boolean);
}

export function splitIntoChunks(text, maxLength = 900) {
  const source = String(text ?? "").trim();

  if (!source) {
    return [];
  }

  const paragraphs = source
    .split(/\n\s*\n/g)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  const chunks = [];
  let current = "";

  for (const paragraph of paragraphs) {
    const next = current ? `${current}\n\n${paragraph}` : paragraph;

    if (next.length <= maxLength) {
      current = next;
      continue;
    }

    if (current) {
      chunks.push(current);
      current = "";
    }

    if (paragraph.length <= maxLength) {
      current = paragraph;
      continue;
    }

    const sentences = paragraph.split(/(?<=[.!?。！？])\s+/);
    let sentenceChunk = "";

    for (const sentence of sentences) {
      const candidate = sentenceChunk ? `${sentenceChunk} ${sentence}` : sentence;

      if (candidate.length <= maxLength) {
        sentenceChunk = candidate;
        continue;
      }

      if (sentenceChunk) {
        chunks.push(sentenceChunk);
      }

      sentenceChunk = sentence;
    }

    if (sentenceChunk) {
      current = sentenceChunk;
    }
  }

  if (current) {
    chunks.push(current);
  }

  return chunks;
}

export function recencyScore(timestamp, now = Date.now()) {
  const createdAt = new Date(timestamp).getTime();

  if (!Number.isFinite(createdAt)) {
    return 0;
  }

  const ageDays = Math.max(0, (now - createdAt) / (1000 * 60 * 60 * 24));
  return 1 / (1 + ageDays / 14);
}

export function clamp(value, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value));
}
