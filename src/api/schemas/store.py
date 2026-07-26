from pydantic import BaseModel, ConfigDict


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str
    domain: str
    base_url: str
    search_endpoint: str
    currency: str
    currency_symbol: str
    active: bool
