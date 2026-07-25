import sys
from pathlib import Path

# Add project root and dags to sys.path
root_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_path / "src"))
sys.path.insert(0, str(root_path / "dags"))

from scheduled_scraper_dag import execute_due_scrape_targets


def main():
    print("Testing Airflow task callable `execute_due_scrape_targets`...")
    execute_due_scrape_targets(limit=5, max_pages=2)
    print("Airflow task execution test completed successfully.")


if __name__ == "__main__":
    main()
