import re
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import chromadb

# Files that use the structured "==== HEADER ====" Q&A format.
# These get split by section, not by raw character count, so each
# chunk stays a single self-contained question + answer.
STRUCTURED_FILES = [
    "docs/sahachari_knowledge_base.txt",
]

# Files that are plain technical docs without that structure — these
# keep using the generic recursive character splitter.
GENERIC_FILES = [
    "docs/customer_api.txt",
    "docs/storekeeper_api.txt",
    "docs/delivery_api.txt",
    "docs/superadmin_api.txt",
]

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)

embedding_model = SentenceTransformer("BAAI/bge-base-en-v1.5")

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="sahachari_docs")


def split_by_sections(text: str) -> list[str]:
    """
    Split a knowledge-base file into one chunk per '==== HEADER ====' section.
    Each returned chunk includes its own header line, so the embedding for
    that chunk captures both the question and its full answer together,
    instead of being diluted by neighboring unrelated sections.

    Matches the literal separator-header-separator-body pattern directly,
    so it doesn't break if there's stray content before the first separator
    (unlike a naive alternating-position split on '====').
    """
    pattern = re.compile(
        r"={5,}\s*\n([^\n]+)\n={5,}\s*\n(.*?)(?=\n={5,}|\Z)",
        re.DOTALL,
    )
    matches = pattern.findall(text)
    sections = [f"{header.strip()}\n{body.strip()}" for header, body in matches]

    # Preserve any leading content before the first separator as its own
    # chunk, so nothing gets silently dropped (e.g. a stray note at the top).
    first_sep_idx = text.find("====")
    if first_sep_idx > 0:
        leading = text[:first_sep_idx].strip()
        if leading:
            sections.insert(0, leading)

    return [s for s in sections if s]


chunk_count = 0

for file in STRUCTURED_FILES:
    print(f"Processing {file} (section-based chunking)")
    with open(file, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = split_by_sections(text)
    print(f"  -> {len(chunks)} section chunks")

    for i, chunk in enumerate(chunks):
        embedding = embedding_model.encode(chunk).tolist()
        collection.upsert(
            ids=[f"{os.path.basename(file)}_{i}"],
            documents=[chunk],
            metadatas=[{"source": file}],
            embeddings=[embedding],
        )
        chunk_count += 1

for file in GENERIC_FILES:
    print(f"Processing {file} (character-based chunking)")
    with open(file, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = splitter.split_text(text)
    print(f"  -> {len(chunks)} chunks")

    for i, chunk in enumerate(chunks):
        embedding = embedding_model.encode(chunk).tolist()
        collection.upsert(
            ids=[f"{os.path.basename(file)}_{i}"],
            documents=[chunk],
            metadatas=[{"source": file}],
            embeddings=[embedding],
        )
        chunk_count += 1

print(f"\nTotal chunks stored: {chunk_count}")
print("Knowledge Base Created Successfully")
