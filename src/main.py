from scrapers.http_client import HttpClient
from scrapers.mdcomputers.scraper import MDComputersScraper


def main():

    with HttpClient() as client:

        scraper = MDComputersScraper(client)

        scraper.scrape_search("graphics-card")


if __name__ == "__main__":
    main()