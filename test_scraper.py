import json
from unittest.mock import MagicMock, patch, mock_open
import pytest
import requests
from advanced_scraper import BookScraper


SAMPLE_HTML = """
<html>
  <body>
    <article class="product_pod">
      <h3><a href="catalogue/book_1/index.html" title="A Great Book">A Great...</a></h3>
      <p class="star-rating Four"></p>
      <p class="price_color">£25.50</p>
      <p class="instock availability">In stock</p>
    </article>
    <article class="product_pod">
      <h3><a href="catalogue/book_2/index.html" title="Another Book">Another...</a></h3>
      <p class="star-rating Two"></p>
      <p class="price_color">£12.00</p>
      <p class="instock availability">Out of stock</p>
    </article>
  </body>
</html>
"""


@pytest.fixture
def scraper():
    return BookScraper(base_url="http://books.toscrape.com/", log_file="test_scraper.log")


# Тестування статичних методів парсингу
def test_parse_rating_all_cases():
    assert BookScraper.parse_rating(["star-rating", "One"]) == 1
    assert BookScraper.parse_rating(["star-rating", "Two"]) == 2
    assert BookScraper.parse_rating(["star-rating", "THREE"]) == 3
    assert BookScraper.parse_rating(["star-rating", "four"]) == 4
    assert BookScraper.parse_rating(["star-rating", "Five"]) == 5
    assert BookScraper.parse_rating(["star-rating", "Unknown"]) == 0
    assert BookScraper.parse_rating([]) == 0


def test_parse_price_cleaning():
    assert BookScraper.parse_price("£51.77") == 51.77
    assert BookScraper.parse_price("$19.99") == 19.99
    assert BookScraper.parse_price("100.50 грн") == 100.50
    assert BookScraper.parse_price("без ціни") == 0.0


# Тестування fetch_page та обробки винятків
def test_fetch_page_success(scraper):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html>Test</html>"
    mock_response.apparent_encoding = "utf-8"

    with patch.object(scraper.session, "get", return_value=mock_response):
        content = scraper.fetch_page("http://test.com")
        assert content == "<html>Test</html>"


def test_fetch_page_http_error(scraper):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")

    with patch.object(scraper.session, "get", return_value=mock_response):
        content = scraper.fetch_page("http://test.com/notfound")
        assert content is None


def test_fetch_page_connection_error(scraper):
    with patch.object(scraper.session, "get", side_effect=requests.exceptions.ConnectionError("Failed to connect")):
        content = scraper.fetch_page("http://invalid.domain")
        assert content is None


def test_fetch_page_timeout(scraper):
    with patch.object(scraper.session, "get", side_effect=requests.exceptions.Timeout("Request timed out")):
        content = scraper.fetch_page("http://slow.server")
        assert content is None


# Тестування парсингу HTML
def test_parse_page_extracts_all_books(scraper):
    books = scraper.parse_page(SAMPLE_HTML, "http://books.toscrape.com/")
    assert len(books) == 2

    first = books[0]
    assert first["title"] == "A Great Book"
    assert first["price"] == 25.50
    assert first["rating"] == 4
    assert first["availability"] == "In stock"
    assert first["link"] == "http://books.toscrape.com/catalogue/book_1/index.html"

    second = books[1]
    assert second["title"] == "Another Book"
    assert second["price"] == 12.00
    assert second["rating"] == 2
    assert second["availability"] == "Out of stock"


def test_parse_page_empty_html(scraper):
    assert scraper.parse_page("", "http://test.com") == []


# Тестування scrape_page
def test_scrape_page_success(scraper):
    with patch.object(scraper, "fetch_page", return_value=SAMPLE_HTML):
        books = scraper.scrape_page(1)
        assert len(books) == 2


def test_scrape_page_failure(scraper):
    with patch.object(scraper, "fetch_page", return_value=None):
        books = scraper.scrape_page(999)
        assert books == []


# Тестування багатопоточного збору
def test_scrape_pages_concurrent(scraper):
    fake_page_books = [{"title": f"Book on page {i}", "price": 10.0, "rating": 3} for i in range(1, 4)]

    def mock_scrape(page_num):
        return [fake_page_books[page_num - 1]]

    with patch.object(scraper, "scrape_page", side_effect=mock_scrape):
        results = scraper.scrape_pages_concurrent(start_page=1, end_page=3)
        assert len(results) == 3
        assert len(scraper.books) == 3


# Тестування фільтрації
def test_filter_books(scraper):
    dataset = [
        {"title": "Book A", "price": 10.0, "rating": 2},
        {"title": "Book B", "price": 35.0, "rating": 4},
        {"title": "Book C", "price": 50.0, "rating": 5},
        {"title": "Book D", "price": 80.0, "rating": 3},
    ]

    filtered_price = scraper.filter_books(min_price=30.0, max_price=60.0, data=dataset)
    assert len(filtered_price) == 2
    assert [b["title"] for b in filtered_price] == ["Book B", "Book C"]

    filtered_rating = scraper.filter_books(min_rating=4, data=dataset)
    assert len(filtered_rating) == 2
    assert [b["title"] for b in filtered_rating] == ["Book B", "Book C"]


# Тестування збереження даних
def test_save_to_csv_success(scraper):
    dataset = [{"title": "Book 1", "price": 10.0, "rating": 5, "availability": "In stock", "link": "http://link"}]
    with patch("builtins.open", mock_open()) as mocked_file:
        status = scraper.save_to_csv("test.csv", data=dataset)
        assert status is True
        mocked_file.assert_called_once_with("test.csv", "w", newline="", encoding="utf-8")


def test_save_to_csv_empty_data(scraper):
    status = scraper.save_to_csv("empty.csv", data=[])
    assert status is False


def test_save_to_csv_io_error(scraper):
    dataset = [{"title": "Book 1", "price": 10.0}]
    with patch("builtins.open", side_effect=IOError("Permission denied")):
        status = scraper.save_to_csv("protected.csv", data=dataset)
        assert status is False


def test_save_to_json_success(scraper):
    dataset = [{"title": "Book 1", "price": 10.0}]
    with patch("builtins.open", mock_open()) as mocked_file:
        status = scraper.save_to_json("test.json", data=dataset)
        assert status is True
        mocked_file.assert_called_once_with("test.json", "w", encoding="utf-8")


def test_save_to_json_empty_data(scraper):
    status = scraper.save_to_json("empty.json", data=[])
    assert status is False


def test_save_to_json_io_error(scraper):
    dataset = [{"title": "Book 1", "price": 10.0}]
    with patch("builtins.open", side_effect=IOError("Disk full")):
        status = scraper.save_to_json("protected.json", data=dataset)
        assert status is False


def test_run_advanced_scraper_entrypoint():
    from advanced_scraper import run_advanced_scraper
    with patch.object(BookScraper, "scrape_pages_concurrent", return_value=[]), \
         patch.object(BookScraper, "save_to_json", return_value=True), \
         patch.object(BookScraper, "save_to_csv", return_value=True), \
         patch.object(BookScraper, "filter_books", return_value=[]):
        run_advanced_scraper()
