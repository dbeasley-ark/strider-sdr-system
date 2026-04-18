# 03 · Retrieval Engineering

RAG is not plug-and-play. Retrieval quality is the ceiling on your agent's answers — the model cannot tell the difference between relevant context and noise, and will happily produce a confident answer from garbage.

## The three pillars

1. **Chunking.** Too large and signal-to-noise drops. Too small and the agent loses the context around a fact. Start with semantic chunking (split at paragraph / section boundaries) before reaching for fixed-size windows.
2. **Embedding.** The model must map related concepts near each other. Test with your actual corpus before committing — different embedding models have dramatically different behaviors on code vs. prose vs. multilingual content.
3. **Re-ranking.** This is the single biggest RAG improvement most systems are missing. Over-fetch initial candidates (e.g. 30), rerank them with a cross-encoder, take the top 5. The cost is tiny; the quality gain is large.

## First question to ask

Before building RAG: is there a structured source of truth that a tool call could query directly? A database, an API, a spreadsheet? Structured queries beat embedding search whenever they're available. RAG is for when the answer lives in unstructured documents.

## Evaluating retrieval

Measure recall@k on a labeled set before you care about end-to-end agent quality. If your retriever has 40% recall@5, your agent is doomed no matter how good the LLM is.
