"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List

# Resource schema for storing crawled documents/web pages or pasted text
class Resource(BaseModel):
    """
    Resources collection schema
    Collection name: "resource"
    """
    title: str = Field(..., description="Title for the resource")
    url: Optional[HttpUrl] = Field(None, description="URL of the resource if from the web")
    content: str = Field(..., description="Extracted plain text content")
    tags: Optional[List[str]] = Field(default=None, description="Optional tags for filtering")

# Example schemas (kept for reference)
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = None
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
