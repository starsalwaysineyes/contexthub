import { clamp, tokenize } from "../utils/text.js";

export function lexicalScore(query, text) {
  const queryTokens = tokenize(query);
  const textTokens = tokenize(text);

  if (queryTokens.length === 0 || textTokens.length === 0) {
    return 0;
  }

  const querySet = new Set(queryTokens);
  const textSet = new Set(textTokens);
  let overlap = 0;

  for (const token of querySet) {
    if (textSet.has(token)) {
      overlap += 1;
    }
  }

  return overlap / querySet.size;
}

export function cosineSimilarity(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length || left.length === 0) {
    return 0;
  }

  let dot = 0;
  let leftMagnitude = 0;
  let rightMagnitude = 0;

  for (let index = 0; index < left.length; index += 1) {
    dot += left[index] * right[index];
    leftMagnitude += left[index] * left[index];
    rightMagnitude += right[index] * right[index];
  }

  if (leftMagnitude === 0 || rightMagnitude === 0) {
    return 0;
  }

  return clamp(dot / (Math.sqrt(leftMagnitude) * Math.sqrt(rightMagnitude)));
}

export function manualScore(record) {
  const importance = clamp((Number(record.importance) || 0) / 5);
  const pinnedBoost = record.pinned ? 1 : 0;
  const curatedBoost = record.manualSummary ? 0.5 : 0;

  return clamp(importance * 0.6 + pinnedBoost * 0.3 + curatedBoost * 0.1);
}
