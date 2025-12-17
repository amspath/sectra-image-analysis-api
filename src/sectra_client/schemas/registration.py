from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from sectra_client.schemas.common import InputType


class TaggedPolygonInputContent(BaseModel):
    """Model for tagged polygon input template content."""

    tags: List[str]


class InputTemplate(BaseModel):
    """Model for input templates."""

    type: InputType
    content: Optional[TaggedPolygonInputContent] = None


class Registration(BaseModel):
    """Model for Sectra registration."""

    applicationId: str
    displayName: str
    manufacturer: str
    url: str
    inputTemplate: InputTemplate
    context: Dict[str, Any] = Field(default_factory=dict)
