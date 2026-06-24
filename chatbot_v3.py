from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer
from FlagEmbedding import FlagReranker
from transformers import pipeline

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

print("Connecting to ChromaDB...")

client = PersistentClient(
    path="./chroma_db"
)

collection = client.get_collection(
    "sahachari_docs"
)

print("\nSahachari AI Assistant Ready!")
print("Type 'exit' to quit.\n")

while True:

    query = input("You: ")

    if query.lower() == "exit":
        break

    greetings = [
        "hi",
        "hello",
        "hey",
        "good morning",
        "good evening",
        "good afternoon"
    ]

    if query.lower() in greetings:
        print("\nAssistant: Hello! How can I help you?\n")
        continue

    try:

        query_embedding = embedding_model.encode(
            query
        ).tolist()

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5
        )

        docs = results["documents"][0]

        scores = reranker.compute_score(
            [[query, doc] for doc in docs]
        )

        ranked_docs = sorted(
            zip(docs, scores),
            key=lambda x: x[1],
            reverse=True
        )

        top_chunks = [
            doc[:500]
            for doc, score in ranked_docs[:2]
        ]

        context = "\n".join(top_chunks)

        print("\n===== RETRIEVED CONTEXT =====\n")
        print(context[:1000])
        print("\n=============================\n")
        prompt = f"""
You are a documentation-based assistant.

RULES:
- Answer ONLY using the provided context.
- Do NOT use external knowledge.
- If the answer is not in the context, reply exactly:
  "Not found in documentation."
- Do not guess or add information that is not present.
- Keep the answer short and precise.

CONTEXT:
{context}

QUESTION:
{query}

ANSWER:
"""

        response = generator(
    prompt,
    max_new_tokens=40,
    do_sample=False,
    temperature=None,
    top_p=None,
    top_k=None,
    return_full_text=False,
    eos_token_id=generator.tokenizer.eos_token_id
)

        final_answer = response[0][
            "generated_text"
        ].strip()

        print("\nAssistant:")
        print(final_answer)

        print("\nSource Context:")
        print("-" * 50)

        for i, (doc, score) in enumerate(ranked_docs[:2], start=1):
            print(f"\nChunk {i} | Score: {score:.4f}")
            print(doc[:300])

        print("\n" + "=" * 80 + "\n")

    except Exception as e:
        print(f"\nError: {e}\n")