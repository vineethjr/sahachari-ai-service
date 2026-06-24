from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer
from FlagEmbedding import FlagReranker
from transformers import pipeline

# ==========================
# Load Models Once
# ==========================

print("Loading Embedding Model...")
embedding_model = SentenceTransformer(
    "BAAI/bge-base-en-v1.5"
)

print("Loading Reranker...")
reranker = FlagReranker(
    "BAAI/bge-reranker-base"
)

print("Loading Qwen...")
generator = pipeline(
    "text-generation",
    model="Qwen/Qwen2.5-0.5B-Instruct"
)

# ==========================
# Connect ChromaDB
# ==========================

print("Connecting to ChromaDB...")

client = PersistentClient(
    path="./chroma_db"
)

collection = client.get_collection(
    "sahachari_docs"
)

print("Collection Size:", collection.count())

def get_answer(query):

    # Create embedding
    query_embedding = embedding_model.encode(
        query
    ).tolist()

    # Retrieve more chunks
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=15
    )

    docs = results["documents"][0]
    metadatas = results["metadatas"][0]

    # Rerank
    scores = reranker.compute_score(
    [[query, doc] for doc in docs]
)

    ranked_results = sorted(
    zip(docs, metadatas, scores),
    key=lambda x: x[2],
    reverse=True
)
    best_doc = ranked_results[0][0]
    best_metadata = ranked_results[0][1]

    # Debugging
    print("\n===== TOP RERANKED CHUNKS =====")

    for i, (doc, metadata, score) in enumerate(ranked_results[:5]):
        print(f"\nChunk {i+1}")
        print("Score:", score)
        print("Source:", metadata["source"])
        print(doc[:300])

    # Top 3 chunks
    top_chunks = [
    doc
    for doc, meta, score in ranked_results[:3]
]

    best_chunk = ranked_results[0][0]

    context = "\n\n".join(top_chunks)

    prompt = f"""
You are Sahachari AI Assistant.

Answer ONLY from the provided context.

Rules:
- Do not use outside knowledge.
- Do not guess.
- If answer not found, say:
  "I could not find that information in the documentation."
- Keep answers concise.
- Mention endpoints if present.
- Mention required fields if present.

Context:
{context}

Question:
{query}

Answer:
"""

    response = generator(
        prompt,
        max_new_tokens=60,
        do_sample=False,
        return_full_text=False
    )

    answer = response[0]["generated_text"].strip()

    return {
    "answer": answer,
    "source": best_metadata["source"]
}