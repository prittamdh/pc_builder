from abc import ABC, abstractmethod


class BaseParser(ABC):

    @abstractmethod
    def parse_search(self, html: str):
        raise NotImplementedError

    @abstractmethod
    def parse_product(self, html: str):
        raise NotImplementedError