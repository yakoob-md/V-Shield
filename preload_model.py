import os
from sentence_transformers import SentenceTransformer

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

def main():
    print(f"⏳ Pre-downloading and caching embedding model: '{MODEL_NAME}'...")
    # Force caching to the current directory's .cache folder if configured
    cache_folder = os.getenv("HF_HOME", None)
    if cache_folder:
        print(f"📦 Caching model weights in: {cache_folder}")
    model = SentenceTransformer(MODEL_NAME)
    print("✅ Embedding model preloaded and cached successfully!")

if __name__ == "__main__":
    main()
