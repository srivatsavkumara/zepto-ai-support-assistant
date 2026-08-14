"""
fixtures.py
-----------
Local HTML mirror of books.toscrape.com used ONLY because this sandbox
cannot reach the internet (host_not_allowed). The HTML markup below
uses the EXACT same tags/classes as the real site
(article.product_pod, p.price_color, p.star-rating <Word>,
p.instock.availability) so the scraping code in the notebook is
IDENTICAL to what you'd run against the live site with internet access.

I (as the "student") generated this fixture data with a small random
generator so I'd have >60 rows across 4 categories to practice on,
and deliberately threw in a few "dirty" rows to test my cleaning code.
"""
import random

random.seed(42)  # so the same "random" data comes out every run

CATEGORIES = {
    "Mystery": "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
    "Fiction": "https://books.toscrape.com/catalogue/category/books/fiction_10/index.html",
    "Fantasy": "https://books.toscrape.com/catalogue/category/books/fantasy_19/index.html",
    "Science": "https://books.toscrape.com/catalogue/category/books/science_22/index.html",
}

STAR_WORDS = ["One", "Two", "Three", "Four", "Five"]

TITLE_PARTS_1 = ["The", "A", "Whispers", "Shadow", "Silent", "Broken", "Hidden",
                 "Last", "Secret", "Midnight", "Winter's", "Forgotten", "Lost",
                 "Golden", "Crimson", "Distant", "Quiet"]
TITLE_PARTS_2 = ["Garden", "Kingdom", "Journey", "House", "River", "Storm",
                  "Letter", "City", "Star", "Door", "Chronicles", "Path",
                  "Song", "Machine", "Portrait", "Voyage", "Prophecy"]


def _make_title(i):
    return f"{random.choice(TITLE_PARTS_1)} {random.choice(TITLE_PARTS_2)} {i}"


def _make_product_pod(title, price_text, star_word, availability_text):
    return f"""
    <article class="product_pod">
        <div class="image_container">
            <a href="../../{title.replace(' ', '-')}_1/index.html">
                <img src="../../../media/cache/placeholder.jpg" alt="{title}">
            </a>
        </div>
        <p class="star-rating {star_word}"></p>
        <h3><a href="../../{title.replace(' ', '-')}_1/index.html" title="{title}">{title}</a></h3>
        <div class="product_price">
            <p class="price_color">{price_text}</p>
            <p class="instock availability">
                <i class="icon-ok"></i>
                {availability_text}
            </p>
        </div>
    </article>
    """


def build_category_page_html(category_name, n_books=18):
    """Builds one listing page with n_books product_pods for a category.
    A couple of rows are deliberately 'dirty' to exercise the cleaning code.
    """
    pods = []
    for i in range(1, n_books + 1):
        title = f"{category_name}: {_make_title(i)}"
        price = round(random.uniform(10, 60), 2)
        price_text = f"£{price}"
        star_word = random.choice(STAR_WORDS)
        in_stock = random.random() > 0.15
        availability_text = (
            f"In stock ({random.randint(1, 22)} available)" if in_stock else "Out of stock"
        )

        # inject a few dirty rows to prove the cleaning step actually works
        if i == 5:
            price_text = "£Â39.99"          # weird encoding, still has a number -> should parse
        if i == 9:
            star_word = "Zero"               # invalid rating word -> row should be dropped
        if i == 13:
            price_text = "Price on request"  # unparseable price -> should get median-imputed

        pods.append(_make_product_pod(title, price_text, star_word, availability_text))

    return f"""
    <html><body>
    <div class="page_inner">
        <div class="row">
            {''.join(pods)}
        </div>
    </div>
    </body></html>
    """


def get_all_fixture_pages():
    """Returns {url: html} for every category listing page (no 'next' link,
    so the paginator in the real scraper naturally stops after page 1
    in offline/demo mode)."""
    pages = {}
    for cat_name, url in CATEGORIES.items():
        pages[url] = build_category_page_html(cat_name, n_books=18)
    return pages
