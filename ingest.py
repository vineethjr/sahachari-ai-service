from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import chromadb
import os

doc_files = [
    "docs/customer_api.txt",
    "docs/storekeeper_api.txt",
    "docs/delivery_api.txt",
    "docs/superadmin_api.txt"
]

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=300
)

embedding_model = SentenceTransformer(
    "BAAI/bge-base-en-v1.5"
)

client = chromadb.PersistentClient(
    path="./chroma_db"
)

# Delete old collection if exists
try:
    client.delete_collection("sahachari_docs")
    print("Old collection deleted.")
except:
    pass

collection = client.create_collection(
    name="sahachari_docs"
)

chunk_count = 0

for file in doc_files:

    print(f"Processing {file}")

    with open(file, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = splitter.split_text(text)

    print(f"Chunks created: {len(chunks)}")

    for i, chunk in enumerate(chunks):

        embedding = embedding_model.encode(
            chunk
        ).tolist()

        collection.add(
            ids=[
                f"{os.path.basename(file)}_{i}"
            ],
            documents=[
                chunk
            ],
            metadatas=[
                {
                    "source": os.path.basename(file)
                }
            ],
            embeddings=[
                embedding
            ]
        )

        chunk_count += 1

print("\n=========================")
print(f"Total chunks stored: {chunk_count}")
print("=========================")
print("Knowledge Base Created Successfully")