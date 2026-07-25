from pydantic import BaseModel

class Store(BaseModel):
    id: int
    name: str
    display_name: str
    domain: str
    base_url: str
    currency: str
    currency_symbol: str

    search_config: dict
    product_config: dict

    active: bool