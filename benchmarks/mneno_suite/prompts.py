"""Prompt templates reserved for later judge-based Mneno suite tasks."""

CONTEXT_ANSWER_PROMPT = """Use only the selected memories to answer the query.

Memories:
{context}

Query: {query}
"""
