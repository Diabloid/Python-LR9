from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import logging
import re
import sys
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class BookScraper:
    RATING_MAP = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
    }

    def __init__(
        self,
        base_url: str = "http://books.toscrape.com/",
        log_file: str = "scraper.log",
        max_workers: int = 4,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.max_workers = max_workers
        self.books: List[Dict[str, Any]] = []
        self.session = requests.Session()
        self.logger = self._setup_logger(log_file)

    def _setup_logger(self, log_file: str) -> logging.Logger:
        logger = logging.getLogger(f"BookScraper_{id(self)}")
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            formatter = logging.Formatter(
                fmt="[%(asctime)s] [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        return logger

    @classmethod
    def parse_rating(cls, star_classes: List[str]) -> int:
        for cls_name in star_classes:
            lower = cls_name.lower()
            if lower in cls.RATING_MAP:
                return cls.RATING_MAP[lower]
        return 0

    @classmethod
    def parse_price(cls, price_text: str) -> float:
        cleaned = re.sub(r"[^\d.]", "", price_text)
        return float(cleaned) if cleaned else 0.0

    def fetch_page(self, url: str) -> Optional[str]:
        self.logger.info(f"Запит сторінки: {url}")
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding or "utf-8"
            self.logger.info(f"Успішно завантажено {url} (статус {response.status_code})")
            return response.text
        except requests.exceptions.HTTPError as http_err:
            self.logger.error(f"HTTP помилка для {url}: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            self.logger.error(f"Помилка з'єднання з {url}: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            self.logger.error(f"Таймаут очікування для {url}: {timeout_err}")
        except requests.RequestException as req_err:
            self.logger.error(f"Помилка запиту для {url}: {req_err}")
        return None

    def parse_page(self, html_content: str, page_url: str) -> List[Dict[str, Any]]:
        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        parsed_books = []

        for item in soup.select("article.product_pod"):
            title_tag = item.select_one("h3 a")
            title = title_tag.get("title", "").strip() if title_tag else "Невідомо"
            relative_link = title_tag.get("href", "").strip() if title_tag else ""
            full_link = urljoin(page_url, relative_link)

            price_tag = item.select_one("p.price_color")
            price = self.parse_price(price_tag.text) if price_tag else 0.0

            rating_tag = item.select_one("p.star-rating")
            rating_classes = rating_tag.get("class", []) if rating_tag else []
            rating = self.parse_rating(rating_classes)

            stock_tag = item.select_one("p.instock.availability")
            availability = stock_tag.text.strip() if stock_tag else "Невідомо"

            parsed_books.append({
                "title": title,
                "price": price,
                "rating": rating,
                "availability": availability,
                "link": full_link,
            })

        return parsed_books

    def scrape_page(self, page_number: int) -> List[Dict[str, Any]]:
        page_url = f"{self.base_url}catalogue/page-{page_number}.html"
        html = self.fetch_page(page_url)
        if not html:
            self.logger.warning(f"Не вдалося отримати контент для сторінки {page_number}")
            return []
        books = self.parse_page(html, page_url)
        self.logger.info(f"Сторінка {page_number}: знайдено {len(books)} книг")
        return books

    def scrape_pages_concurrent(self, start_page: int = 1, end_page: int = 5) -> List[Dict[str, Any]]:
        start_time = time.time()
        self.logger.info(
            f"Запуск багатопоточного парсингу сторінок {start_page}..{end_page} (потоків: {self.max_workers})"
        )

        all_results = []
        pages = list(range(start_page, end_page + 1))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_page = {
                executor.submit(self.scrape_page, page_num): page_num
                for page_num in pages
            }

            for future in as_completed(future_to_page):
                page_num = future_to_page[future]
                try:
                    books = future.result()
                    all_results.extend(books)
                except Exception as exc:
                    self.logger.error(f"Помилка при обробці сторінки {page_num}: {exc}")

        self.books = all_results
        elapsed = time.time() - start_time
        self.logger.info(
            f"Багатопоточний збір завершено за {elapsed:.2f} сек. Усього зібрано: {len(self.books)} книг"
        )
        return self.books

    def filter_books(
        self,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_rating: Optional[int] = None,
        data: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        target_data = data if data is not None else self.books
        filtered = []

        for book in target_data:
            if min_price is not None and book["price"] < min_price:
                continue
            if max_price is not None and book["price"] > max_price:
                continue
            if min_rating is not None and book["rating"] < min_rating:
                continue
            filtered.append(book)

        self.logger.info(
            f"Фільтрація: вихідних {len(target_data)}, після фільтрації {len(filtered)}"
        )
        return filtered

    def save_to_csv(self, filepath: str, data: Optional[List[Dict[str, Any]]] = None) -> bool:
        target_data = data if data is not None else self.books
        if not target_data:
            self.logger.warning(f"Дані для збереження у CSV порожні ({filepath})")
            return False

        fieldnames = ["title", "price", "rating", "availability", "link"]
        try:
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(target_data)
            self.logger.info(f"Збережено {len(target_data)} записів у CSV: {filepath}")
            return True
        except IOError as err:
            self.logger.error(f"Помилка запису у CSV {filepath}: {err}")
            return False

    def save_to_json(self, filepath: str, data: Optional[List[Dict[str, Any]]] = None) -> bool:
        target_data = data if data is not None else self.books
        if not target_data:
            self.logger.warning(f"Дані для збереження у JSON порожні ({filepath})")
            return False

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(target_data, f, ensure_ascii=False, indent=4)
            self.logger.info(f"Збережено {len(target_data)} записів у JSON: {filepath}")
            return True
        except IOError as err:
            self.logger.error(f"Помилка запису у JSON {filepath}: {err}")
            return False


def run_advanced_scraper() -> None:
    scraper = BookScraper(max_workers=5)

    # Багатопоточний збір 5 сторінок (100 книг)
    scraped_books = scraper.scrape_pages_concurrent(start_page=1, end_page=5)

    # Збереження у JSON та CSV
    scraper.save_to_json("advanced_books.json")
    scraper.save_to_csv("advanced_books.csv")

    # Фільтрація: преміум книги з рейтингом 5 зірок та ціною > 40.0
    top_books = scraper.filter_books(min_price=40.0, min_rating=5)
    scraper.save_to_json("top_rated_books.json", data=top_books)
    scraper.save_to_csv("top_rated_books.csv", data=top_books)


if __name__ == "__main__":
    run_advanced_scraper()
