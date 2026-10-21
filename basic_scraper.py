import sys
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_URL = "http://books.toscrape.com/"


def run_basic_scraper(url: str = BASE_URL, output_file: str = "scraped_data.txt") -> None:
    # Завантаження HTML-сторінки
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"

    # Створення об'єкта BeautifulSoup для парсингу HTML
    soup = BeautifulSoup(response.text, "html.parser")

    # Витяг заголовка сторінки
    page_title = soup.title.string.strip() if soup.title else "Без назви"
    print(f"Заголовок сторінки: {page_title}")

    # Витяг інформації про книги на поточній сторінці
    book_articles = soup.select("article.product_pod")
    books = []
    for book in book_articles:
        title_element = book.select_one("h3 a")
        price_element = book.select_one("p.price_color")

        title = title_element.get("title", "").strip() if title_element else "Невідомо"
        price = price_element.text.strip() if price_element else "Невідомо"
        books.append((title, price))

    # Витяг усіх посилань зі сторінки
    all_links = []
    for link_tag in soup.find_all("a", href=True):
        raw_href = link_tag.get("href", "").strip()
        absolute_href = urljoin(url, raw_href)
        link_text = " ".join(link_tag.text.split())
        all_links.append((link_text or "Без тексту", absolute_href))

    # Виведення отриманих даних у консоль у структурованому вигляді
    print(f"\nЗнайдено книг на сторінці: {len(books)}")
    for index, (title, price) in enumerate(books[:5], start=1):
        print(f"  {index}. {title} — Ціна: {price}")
    if len(books) > 5:
        print(f"  ... та ще {len(books) - 5} книг")

    print(f"\nЗнайдено посилань на сторінці: {len(all_links)}")
    for index, (text, href) in enumerate(all_links[:5], start=1):
        print(f"  {index}. [{text}] -> {href}")
    if len(all_links) > 5:
        print(f"  ... та ще {len(all_links) - 5} посилань")

    # Збереження результатів у простий текстовий файл
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"Звіт парсингу базового рівня\n")
        f.write(f"URL сторінки: {url}\n")
        f.write(f"Заголовок: {page_title}\n\n")

        f.write(f"Список знайдених книг ({len(books)}):\n")
        for index, (title, price) in enumerate(books, start=1):
            f.write(f"{index}. {title} | {price}\n")

        f.write(f"\nУсі гіперпосилання зі сторінки ({len(all_links)}):\n")
        for index, (text, href) in enumerate(all_links, start=1):
            f.write(f"{index}. [{text}] -> {href}\n")

    print(f"\nДані успішно збережено у файл: {output_file}")


if __name__ == "__main__":
    run_basic_scraper()
