"""
build_index.py
Run this ONCE to precompute embeddings for every chunk in your knowledge base.
Output: index.json  (chunks + their vectors)  -> loaded instantly by the server.

Usage:
    export MISTRAL_API_KEY=your_key_here
    python build_index.py knowledge_base.json
"""
import os, sys, json, time
from mistralai import Mistral

def _load_dotenv():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_dotenv()

API_KEY = os.environ.get("MISTRAL_API_KEY")
if not API_KEY:
    sys.exit("Set MISTRAL_API_KEY first (in a .env file or:  export MISTRAL_API_KEY=...)")

EMBED_MODEL = "mistral-embed"
client = Mistral(api_key=API_KEY)

def embed_batch(texts):
    """Embed a list of texts, with simple retry for free-tier rate limits."""
    for attempt in range(6):
        try:
            resp = client.embeddings.create(model=EMBED_MODEL, inputs=texts)
            return [d.embedding for d in resp.data]
        except Exception as e:
            wait = 2 ** attempt
            print(f"  embed retry {attempt+1} ({e}); sleeping {wait}s")
            time.sleep(wait)
    raise RuntimeError("Embedding failed after retries")

def main(kb_path):
    with open(kb_path, encoding="utf-8") as f:
        kb = json.load(f)

    chunks = kb["chunks"]
    print(f"Loaded {len(chunks)} chunks from {kb_path}")

    # Embed in small batches (free tier friendly)
    BATCH = 16
    vectors = []
    for i in range(0, len(chunks), BATCH):
        batch = chunks[i:i+BATCH]
        texts = [c["text"] for c in batch]
        print(f"Embedding chunks {i}..{i+len(batch)-1}")
        vectors.extend(embed_batch(texts))
        time.sleep(0.5)  # gentle pacing for the free tier

    index = {
        "video_id": kb.get("video_id"),
        "language": kb.get("language", "fa"),
        "model": EMBED_MODEL,
        "items": [
            {
                "chunk_id": c["chunk_id"],
                "text": c["text"],
                "timestamp": c.get("timestamp"),
                "timestamp_range": c.get("timestamp_range"),
                "start_seconds": c.get("start_seconds"),
                "vector": v,
            }
            for c, v in zip(chunks, vectors)
        ],
    }

    with open("index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    print(f"\nWrote index.json with {len(index['items'])} vectors "
          f"(dim={len(vectors[0])})")

if __name__ == "__main__":
    kb = sys.argv[1] if len(sys.argv) > 1 else "knowledge_base.json"
    main(kb)