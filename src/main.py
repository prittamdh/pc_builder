from scrapers.sites.mdcomputers import MDComputersScraper


def main():

    scraper = MDComputersScraper()

    html = scraper.search("RTX 5070")

    print(html[:1000])


if __name__ == "__main__":
    main()