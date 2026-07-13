from pydantic import BaseModel, Field


class ProductMapping(BaseModel):
    source_name: str
    normalized_source_name: str
    one_c_product_id: str
    one_c_product_name: str