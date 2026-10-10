from pydantic import BaseModel, Field
from pydantic import ConfigDict


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=0)
    gender: str = Field(min_length=1, max_length=20)


class CustomerResponse(CustomerCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)

class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    age: int | None = Field(default=None, ge=0)
    gender: str | None = Field(default=None, min_length=1, max_length=20)