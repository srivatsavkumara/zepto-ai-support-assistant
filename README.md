IML Course Project — Submission Repository

Single repository, 3 independent module folders, each self-contained with its own README, code, and (where applicable) executed notebook output.

#	Module	Folder	What it is
1	Data Pipeline	/data_pipeline	Scrapes books.toscrape.com, cleans the data, converts GBP→INR at a fixed project rate, loads it into a normalized SQLite DB (2 tables, PK/FK), and runs/cross-checks SQL + pandas queries.
2	Analytics	/analytics	Titanic EDA + predictive modeling pipeline: missing-value handling, univariate/bivariate/multivariate data story, leak-free ColumnTransformer + Pipeline, 3 classifiers compared (Logistic Regression, Decision Tree, Random Forest), imbalance-handling comparison (baseline vs class_weight vs SMOTE), GridSearchCV-tuned Random Forest, a linear-regression side-task on fare, and a saved/reloaded joblib pipeline.
3	Support Assistant	/support_assistant	Offline-gradable RAG service over Zepto's policy documents — LangGraph StateGraph (intent classification → retrieval → generation), ChromaDB + local sentence-transformers embeddings, FastAPI POST /ask endpoint, Dockerized, with a mock-LLM baseline and an optional real-LLM (Groq) extension.
How to use this repo

Each module folder is independent — install steps, run steps, and design-decision writeups all live in that module's own README, linked above. Start there for any module you want to run or grade.

Module summaries
1. /data_pipeline
Deliverable: demo1.ipynb (pre-executed, real output baked in) + data_pipeline.ipynb (re-runnable) + pipeline.py (script form) + books.db (generated SQLite DB).
Scope: 72 books scraped across 4 categories → 68 clean rows after justified cleaning (median-impute vs. drop). 5 SQL queries covering SELECT/WHERE, ORDER BY/LIMIT, DISTINCT, BETWEEN/IN, and a JOIN; the join query is cross-checked against a pure-pandas merge and confirmed to match exactly.
Note: live scraping falls back to a local HTML mirror only if internet is unreachable in the grading environment — the scraping code itself is unchanged either way (see that module's README for detail).
2. /analytics
Deliverable: 01_eda.ipynb → 02_modeling.ipynb (run in that order) + plain-script (.py) equivalents + demo.ipynb (pre-run) + figures/ + titanic_best_pipeline.joblib.
Scope: all 15 tasks from the brief, from missing-value-threshold rules through GridSearchCV tuning, imbalance-strategy comparison, a regression side-task on fare, and a save/reload check on the final fitted pipeline. Full task-by-task checklist is in that module's README.
3. /support_assistant
Deliverable: notebooks 00_setup.ipynb → 04_app.ipynb (each generates a corresponding .py), 05_demo.ipynb as the runner, a Dockerfile, and the 2 required example POST /ask calls with raw JSON output.
Scope: ingestion (8 policy docs) → local MiniLM embeddings → ChromaDB retrieval → LangGraph-routed generation (mock-LLM baseline graded by default; optional real-LLM extension via Groq). Architecture diagram and both example calls are in that module's README.
Submission notes
This root README is the entry point; each module's own README has the full install/run instructions and requirement checklist for that module.
The graded baseline for support_assistant runs with MOCK_LLM left at its default (no API key needed) — see that module's README for the optional real-LLM extension.
Git history requirement (feature branch created, ≥2 commits, merged to main) applies to this repository as a whole, not per module.
