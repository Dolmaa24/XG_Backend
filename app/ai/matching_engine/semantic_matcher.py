from typing import Optional

def calculate_similarity(resume_text: str, job_description: str) -> float:
    """Cosine similarity via sentence-transformers (lazy import — not required at startup)."""
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity

        model = SentenceTransformer("all-MiniLM-L6-v2")
        resume_emb = model.encode([resume_text])
        jd_emb = model.encode([job_description])
        similarity = cosine_similarity(resume_emb, jd_emb)[0][0]
        return round(float(similarity) * 100, 2)
    except ImportError:
        return 0.0
