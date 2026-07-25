from abc import ABC, abstractmethod

from domain.store import Store


class BaseParser(ABC):

    def __init__(self, store: Store):
        self.store = store
        self.search_config = store.search_config
        self.product_config = store.product_config

    @abstractmethod
    def parse_search(self, html: str):
        pass

    @abstractmethod
    def parse_product(self, html: str):
        pass