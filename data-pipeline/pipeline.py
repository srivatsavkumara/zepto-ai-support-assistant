# ==============================================================
# Zepto Data Pipeline Assignment - books.toscrape.com
# Name : (student)
# Note : did this over the holidays after finishing my AIML course,
#        so pls forgive if the code is not super optimized :)
#        I tried to comment every step so I remember what I did later.
# ==============================================================

import sys, os, time, statistics, sqlite3
import requests
from bs4 import BeautifulSoup
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fixtures import get_all_fixture_pages, CATEGORIES

# --------------------------------------------------------------
# STEP 0: CONFIG
# --------------------------------------------------------------
GBP_TO_INR = 105.50   # fixed project baseline rate, no live lookup needed
BASE_URL = "https://books.toscrape.com"

RATING_WORD_TO_NUM = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

FIXTURE_PAGES = get_all_fixture_pages()   # local mirror, used as fallback
USED_FALLBACK = False   # just to print a warning once


# --------------------------------------------------------------
# STEP 1: FETCH A PAGE (real internet first, local fixture fallback)
# --------------------------------------------------------------
def fetch_page(url):
    """Try to actually download the page with requests.
    If that fails (e.g. no internet in this sandbox), fall back to the
    local HTML mirror in fixtures.py so the rest of the pipeline can
    still be tested end to end. On a normal machine with internet this
    fallback never triggers - requests.get() just works.
    """
    global USED_FALLBACK
    try:
        resp = requests.get(url, timeout=6)
        if resp.status_code == 200:
            return resp.text
        else:
            raise Exception(f"bad status code {resp.status_code}")
    except Exception as e:
        if not USED_FALLBACK:
            print(f"[warning] could not reach the internet ({e}).")
            print("[warning] using local fixture HTML instead so the pipeline still runs.")
            USED_FALLBACK = True
        if url in FIXTURE_PAGES:
            return FIXTURE_PAGES[url]
        raise


# --------------------------------------------------------------
# STEP 2: SCRAPE ONE CATEGORY (handles pagination too)
# --------------------------------------------------------------
def scrape_category(category_name, start_url):
    rows = []
    url = start_url
    page_num = 1
    while url:
        html = fetch_page(url)
        soup = BeautifulSoup(html, "html.parser")
        books = soup.select("article.product_pod")
        print(f"  page {page_num} of {category_name}: found {len(books)} books")

        for b in books:
            title = b.h3.a["title"]
            price_text = b.select_one("p.price_color").get_text(strip=True)
            star_tag = b.select_one("p.star-rating")
            star_word = star_tag["class"][1] if star_tag and len(star_tag["class"]) > 1 else None
            availability_text = b.select_one("p.instock.availability").get_text(strip=True)

            rows.append({
                "title": title,
                "price": price_text,
                "star_rating": star_word,
                "availability": availability_text,
                "category": category_name,
            })

        # look for a "next" page link (real site pagination)
        next_link = soup.select_one("li.next a")
        if next_link:
            # real site next hrefs are relative, e.g. "page-2.html"
            url = start_url.rsplit("/", 1)[0] + "/" + next_link["href"]
            page_num += 1
        else:
            url = None
    return rows


def scrape_all_categories(categories_dict):
    all_rows = []
    for cat_name, url in categories_dict.items():
        print(f"scraping category: {cat_name}")
        all_rows.extend(scrape_category(cat_name, url))
    return all_rows


# --------------------------------------------------------------
# STEP 3: RUN THE SCRAPE
# --------------------------------------------------------------
print("=" * 60)
print("STEP 1-2: SCRAPING")
print("=" * 60)
raw_rows = scrape_all_categories(CATEGORIES)
raw_df = pd.DataFrame(raw_rows)
print(f"\nTotal raw rows scraped: {len(raw_df)}")
print(f"Categories scraped: {raw_df['category'].nunique()} -> {list(raw_df['category'].unique())}")
print(raw_df.head())


# --------------------------------------------------------------
# STEP 4: CLEAN THE DATA
# --------------------------------------------------------------
print("\n" + "=" * 60)
print("STEP 3: CLEANING")
print("=" * 60)

df = raw_df.copy()

# 4a. price_gbp: strip everything except digits and the decimal point,
#     then convert to float. Some rows are junk (like "Price on request")
#     - for those I put NaN for now and fix with median imputation below.
def parse_price(price_text):
    import re
    match = re.search(r"[\d]+\.?[\d]*", price_text.replace(",", ""))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None

df["price_gbp"] = df["price"].apply(parse_price)

n_missing_price = df["price_gbp"].isna().sum()
print(f"rows with unparseable price: {n_missing_price}")

# DECISION: median-impute missing prices (rather than drop) because a
# missing/garbled price is usually a display glitch, not bad data about
# the *book itself* - the book is real and still worth keeping in the
# catalog, so I fill it with the median price instead of losing the row.
if n_missing_price > 0:
    median_price = df["price_gbp"].median()
    df["price_gbp"] = df["price_gbp"].fillna(median_price)
    print(f"imputed {n_missing_price} missing price(s) with median = {median_price:.2f}")

# 4b. rating: One..Five -> 1..5. If the word isn't valid (like my fake
# "Zero" dirty row), I can't guess a rating out of thin air, so I DROP
# those rows instead of imputing - a made-up star rating would be
# misleading in a ratings analysis (unlike price, which is just a number).
df["rating"] = df["star_rating"].map(RATING_WORD_TO_NUM)
n_bad_rating = df["rating"].isna().sum()
print(f"rows with unrecognised rating word: {n_bad_rating} -> dropping them")
df = df.dropna(subset=["rating"]).copy()
df["rating"] = df["rating"].astype(int)

# 4c. availability -> boolean in_stock
df["in_stock"] = df["availability"].str.lower().str.contains("in stock")

# 4d. price_inr using the fixed project rate (NOT a live API call)
df["price_inr"] = (df["price_gbp"] * GBP_TO_INR).round(2)

# keep only the clean columns we need going forward
clean_df = df[["title", "category", "price_gbp", "price_inr", "rating", "in_stock"]].reset_index(drop=True)

print(f"\nfinal clean row count: {len(clean_df)}")
print(clean_df.dtypes)
print(clean_df.head())


# --------------------------------------------------------------
# STEP 5: BUILD NORMALIZED SQLITE DATABASE
# --------------------------------------------------------------
print("\n" + "=" * 60)
print("STEP 4: LOADING INTO SQLITE (normalized, 2 tables, PK/FK)")
print("=" * 60)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "books.db")
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)  # start fresh every run so this script is repeatable

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("""
CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT UNIQUE NOT NULL
)
""")

cur.execute("""
CREATE TABLE books (
    book_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    price_gbp REAL NOT NULL,
    price_inr REAL NOT NULL,
    rating INTEGER NOT NULL,
    in_stock INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
)
""")

# insert categories first, get back their ids
category_ids = {}
for cat_name in sorted(clean_df["category"].unique()):
    cur.execute("INSERT INTO categories (category_name) VALUES (?)", (cat_name,))
    category_ids[cat_name] = cur.lastrowid

# now insert books, using the category_id we just made
book_rows = []
for _, r in clean_df.iterrows():
    book_rows.append((
        r["title"],
        float(r["price_gbp"]),
        float(r["price_inr"]),
        int(r["rating"]),
        int(bool(r["in_stock"])),
        category_ids[r["category"]],
    ))

cur.executemany("""
    INSERT INTO books (title, price_gbp, price_inr, rating, in_stock, category_id)
    VALUES (?, ?, ?, ?, ?, ?)
""", book_rows)

conn.commit()
print(f"inserted {len(category_ids)} categories and {len(book_rows)} books into {DB_PATH}")


# --------------------------------------------------------------
# STEP 6: SQL QUERIES  (SELECT/WHERE, ORDER BY, LIMIT, DISTINCT, BETWEEN/IN, JOIN)
# --------------------------------------------------------------
print("\n" + "=" * 60)
print("STEP 5: SQL QUERIES")
print("=" * 60)

queries = {}

# Q1: SELECT + WHERE  -> books that are in stock and rated 4 or 5
queries["Q1_instock_high_rated"] = """
SELECT title, rating, price_inr
FROM books
WHERE in_stock = 1 AND rating >= 4
"""

# Q2: ORDER BY + LIMIT -> top 10 most expensive books (in INR)
queries["Q2_top10_expensive"] = """
SELECT title, price_inr
FROM books
ORDER BY price_inr DESC
LIMIT 10
"""

# Q3: DISTINCT -> list every distinct rating value present in the data
queries["Q3_distinct_ratings"] = """
SELECT DISTINCT rating
FROM books
ORDER BY rating
"""

# Q4: BETWEEN (+ IN) -> mid-range priced books in a couple of chosen categories
queries["Q4_between_and_in"] = """
SELECT b.title, b.price_inr, c.category_name
FROM books b
JOIN categories c ON b.category_id = c.category_id
WHERE b.price_inr BETWEEN 2000 AND 4000
  AND c.category_name IN ('Mystery', 'Fantasy')
"""

# Q5: JOIN -> top 3 highest rated books per category (the required join query)
queries["Q5_top_rated_per_category_JOIN"] = """
SELECT c.category_name, b.title, b.rating, b.price_inr
FROM books b
JOIN categories c ON b.category_id = c.category_id
WHERE b.rating = (
    SELECT MAX(b2.rating) FROM books b2 WHERE b2.category_id = b.category_id
)
ORDER BY c.category_name, b.price_inr DESC
"""

query_results = {}
for name, sql in queries.items():
    print(f"\n--- {name} ---")
    print(sql.strip())
    result = cur.execute(sql).fetchall()
    cols = [d[0] for d in cur.description]
    result_df = pd.DataFrame(result, columns=cols)
    query_results[name] = result_df
    print(f"-> {len(result_df)} rows")
    print(result_df.head(10).to_string(index=False))


# --------------------------------------------------------------
# STEP 7: pandas.read_sql + pandas.merge (no-SQL) comparison
# --------------------------------------------------------------
print("\n" + "=" * 60)
print("STEP 6: pandas read_sql vs pandas merge (for the JOIN query)")
print("=" * 60)

# 2 queries read back with pd.read_sql
df_q1_pd = pd.read_sql(queries["Q1_instock_high_rated"], conn)
df_q5_pd = pd.read_sql(queries["Q5_top_rated_per_category_JOIN"], conn)
print("\npd.read_sql(Q1) shape:", df_q1_pd.shape)
print("pd.read_sql(Q5 - the JOIN query) shape:", df_q5_pd.shape)

# now reproduce Q5 using ONLY pandas merge on the in-memory dataframes
categories_df_mem = pd.read_sql("SELECT * FROM categories", conn)
books_df_mem = pd.read_sql("SELECT * FROM books", conn)

merged = books_df_mem.merge(categories_df_mem, on="category_id", how="inner")

# top-rated per category, done the pandas way (no SQL at all)
max_rating_per_cat = merged.groupby("category_id")["rating"].transform("max")
pandas_join_result = merged[merged["rating"] == max_rating_per_cat][
    ["category_name", "title", "rating", "price_inr"]
].sort_values(["category_name", "price_inr"], ascending=[True, False]).reset_index(drop=True)

sql_join_result = df_q5_pd.sort_values(["category_name", "price_inr"], ascending=[True, False]).reset_index(drop=True)

print("\nSQL JOIN result (via pd.read_sql):")
print(sql_join_result.to_string(index=False))
print("\npandas merge result (no SQL):")
print(pandas_join_result.to_string(index=False))

are_equal = sql_join_result.reset_index(drop=True).equals(pandas_join_result.reset_index(drop=True))
print(f"\nSQL result and pandas-merge result match exactly: {are_equal}")

conn.close()
print("\nDONE. Database saved at:", DB_PATH)
