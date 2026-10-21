import csv
import re
import sys
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_CATALOGUE_URL = "http://books.toscrape.com/catalogue/page-{page}.html"

RATING_MAP = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}


def parse_rating(star_classes: List[str]) -> int:
    for cls in star_classes:
        lower_cls = cls.lower()
        if lower_cls in RATING_MAP:
            return RATING_MAP[lower_cls]
    return 0


def parse_price(price_text: str) -> float:
    cleaned = re.sub(r"[^\d.]", "", price_text)
    return float(cleaned) if cleaned else 0.0


def parse_page_books(html_content: str, page_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html_content, "html.parser")
    books = []

    for item in soup.select("article.product_pod"):
        title_tag = item.select_one("h3 a")
        title = title_tag.get("title", "").strip() if title_tag else "Невідомо"
        relative_link = title_tag.get("href", "").strip() if title_tag else ""
        full_link = urljoin(page_url, relative_link)

        price_tag = item.select_one("p.price_color")
        price = parse_price(price_tag.text) if price_tag else 0.0

        rating_tag = item.select_one("p.star-rating")
        rating_classes = rating_tag.get("class", []) if rating_tag else []
        rating = parse_rating(rating_classes)

        stock_tag = item.select_one("p.instock.availability")
        availability = stock_tag.text.strip() if stock_tag else "Невідомо"

        books.append({
            "title": title,
            "price": price,
            "rating": rating,
            "availability": availability,
            "link": full_link,
        })

    return books


def scrape_multiple_pages(start_page: int = 1, end_page: int = 3) -> List[Dict[str, Any]]:
    all_books = []
    print(f"Початок збору даних зі сторінок від {start_page} до {end_page}...")

    for page in range(start_page, end_page + 1):
        url = BASE_CATALOGUE_URL.format(page=page)
        print(f"Завантаження сторінки {page}: {url}")

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            page_books = parse_page_books(response.text, url)
            all_books.extend(page_books)
            print(f"  Зібрано {len(page_books)} книг зі сторінки {page}")
        except requests.RequestException as e:
            print(f"  Помилка завантаження сторінки {page}: {e}")

    print(f"Усього зібрано: {len(all_books)} книг.")
    return all_books


def filter_books(
    books: List[Dict[str, Any]],
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[int] = None,
) -> List[Dict[str, Any]]:
    filtered = []
    for book in books:
        if min_price is not None and book["price"] < min_price:
            continue
        if max_price is not None and book["price"] > max_price:
            continue
        if min_rating is not None and book["rating"] < min_rating:
            continue
        filtered.append(book)
    return filtered


def save_books_to_csv(books: List[Dict[str, Any]], filename: str) -> None:
    if not books:
        print(f"Список книг порожній, файл {filename} не створено.")
        return

    fieldnames = ["title", "price", "rating", "availability", "link"]
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(books)

    print(f"Дані ({len(books)} записів) збережено у файл {filename}")


def run_medium_scraper() -> None:
    # 1. Збір даних з перших 3 сторінок каталогу (60 книг)
    dataset = scrape_multiple_pages(start_page=1, end_page=3)

    # 2. Збереження повного датасету в CSV
    save_books_to_csv(dataset, "books_dataset.csv")

    # 3. Фільтрація: книги з рейтингом не менше 4 зірок та ціною більше 30.0
    filtered = filter_books(dataset, min_price=30.0, min_rating=4)
    print(f"\nКількість книг за фільтром (ціна >= 30.0 та рейтинг >= 4): {len(filtered)}")

    # 4. Збереження відфільтрованого датасету
    save_books_to_csv(filtered, "filtered_books.csv")


if __name__ == "__main__":
    run_medium_scraper()
