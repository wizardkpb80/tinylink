from pydantic import BaseModel

class LinkCreate(BaseModel):
    original_url: str

class LinkResponse(BaseModel):
    short_code: str
    original_url: str
