from abc import ABC, abstractmethod

class BaseParser(ABC):

    @abstractmethod
    def parse_search(self, html: str):
        pass

    @abstractmethod
    def parse_product(self, html: str):
        pass