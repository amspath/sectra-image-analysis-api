from enum import Enum, unique
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, model_validator, field_validator

from sectra_client.schemas.common import CallbackInfo, InputType, Polygon
from sectra_client.schemas.image import ImageMetadata
from sectra_client.schemas.results import ResultResponse


@unique
class Action(str, Enum):
    """Enum of invocation actions"""

    CREATE = "create"
    MODIFY = "modify"
    CANCEL = "cancel"
    DELETE = "delete"


class TaggedPolygonContent(BaseModel):
    """Model for tagged polygon input content."""

    polygon: Polygon
    tags: Optional[List[str]] = None
    tagIndex: Optional[int] = None

    @model_validator(mode="after")
    def validate_tags(self) -> "TaggedPolygonContent":
        if self.tags is not None and self.tagIndex is None:
            raise ValueError("tagIndex must be defined when tags is not None")
        return self


class MultiAreaContent(BaseModel):
    """Model for multi area input content."""

    polygons: List[Polygon]


class CreateInput(BaseModel):
    """Model for create invocation input."""

    type: InputType
    content: Optional[Union[TaggedPolygonContent, MultiAreaContent]] = None

    @model_validator(mode="after")
    def validate_content(self) -> "CreateInput":
        if self.type != InputType.WHOLE_SLIDE and self.content is None:
            raise ValueError("content must be defined when type is not wholeSlide")
        return self


class InvocationBase(BaseModel):
    """Base model for both hook launch and image notification."""

    applicationId: str
    slideId: str
    callbackInfo: CallbackInfo
    context: Dict[str, Any] = Field(default_factory=dict)
    cancellationToken: Optional[str] = None

    @field_validator("context", mode="before")
    @classmethod
    def none_to_dict(cls, v):
        return {} if v is None else v


class Invocation(InvocationBase):
    """Model for invocations from DPAT."""

    action: Action
    input: Optional[Union[CreateInput, ResultResponse]] = None

    @model_validator(mode="after")
    def validate_input(self) -> "Invocation":
        if self.action != Action.CANCEL and self.input is None:
            raise ValueError("input must not be None when action is not cancel")

        if self.action != Action.DELETE and self.cancellationToken is None:
            raise ValueError("cancellationToken must be defined when action is not delete")

        return self


class ImageNotification(InvocationBase):
    """Model for new image notification from DPAT."""

    imageInfo: ImageMetadata

