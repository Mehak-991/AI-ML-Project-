"""AI services: embeddings, transformer inference, LLM chat, token counting.

Every optional third-party package (torch, transformers, sentence-transformers,
openai, tiktoken, langgraph, langchain-text-splitters) is imported lazily inside
functions, so importing this package never requires them and the core API
starts without them.
"""
