FROM python:3.11-slim

WORKDIR /app

# System deps for sentence-transformers / chromadb wheels
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY docs/ ./docs/
COPY 01_ingest.ipynb 02_prompt_template.ipynb 03_graph.ipynb 04_app.ipynb ./

# Source of truth is the notebooks (per assignment requirement). Executing them
# here (in dependency order) runs their %%writefile cells and materializes the
# .py modules (ingest.py, prompt_template.py, schemas.py, graph.py, main.py)
# that uvicorn needs, and builds the ChromaDB collection under ./chroma_db.
# MOCK_LLM defaults to mock mode, so this build step makes no LLM/network calls
# beyond the one-time embedding-model download.
RUN jupyter nbconvert --to notebook --execute --inplace 01_ingest.ipynb && \
    jupyter nbconvert --to notebook --execute --inplace 02_prompt_template.ipynb && \
    jupyter nbconvert --to notebook --execute --inplace 03_graph.ipynb && \
    jupyter nbconvert --to notebook --execute --inplace 04_app.ipynb

EXPOSE 7860

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
