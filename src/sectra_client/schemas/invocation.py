from enum import Enum, unique
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from sectra_client.schemas.common import CallbackInfo, InputType, Polygon
from sectra_client.schemas.image import ImageMetadata
from sectra_client.schemas.results import ResultResponse

NoneToDict = Annotated[dict[str, Any], BeforeValidator(lambda v: v if v is not None else {})]


@unique
class Action(str, Enum):
    CREATE = "create"
    MODIFY = "modify"
    CANCEL = "cancel"
    DELETE = "delete"
    NEW_IMAGE_FILES = "newImageFiles"


class TaggedPolygonContent(BaseModel):
    polygon: Polygon
    tags: list[str] | None = None
    tagIndex: int | None = None

    @model_validator(mode="after")
    def validate_tags(self) -> "TaggedPolygonContent":
        if self.tags is not None and self.tagIndex is None:
            raise ValueError("tagIndex must be defined when tags is not None")
        return self


class MultiAreaContent(BaseModel):
    polygons: list[Polygon]


class WholeSlideInput(BaseModel):
    type: Literal[InputType.WHOLE_SLIDE] = InputType.WHOLE_SLIDE


class TaggedPolygonInput(BaseModel):
    type: Literal[InputType.TAGGED_POLYGON] = InputType.TAGGED_POLYGON
    content: TaggedPolygonContent


class MultiAreaInput(BaseModel):
    type: Literal[InputType.MULTI_AREA] = InputType.MULTI_AREA
    content: MultiAreaContent


CreateInput = Annotated[WholeSlideInput | TaggedPolygonInput | MultiAreaInput, Field(discriminator="type")]


class InvocationBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    applicationId: str
    slideId: str
    callbackInfo: CallbackInfo
    context: NoneToDict = Field(default_factory=dict)
    cancellationToken: str | None = None


class CreateInvocation(InvocationBase):
    action: Literal[Action.CREATE] = Action.CREATE
    cancellationToken: str
    input: CreateInput


class ModifyInvocation(InvocationBase):
    action: Literal[Action.MODIFY] = Action.MODIFY
    cancellationToken: str
    input: ResultResponse


class CancelInvocation(InvocationBase):
    action: Literal[Action.CANCEL] = Action.CANCEL
    cancellationToken: str


class DeleteInvocation(InvocationBase):
    action: Literal[Action.DELETE] = Action.DELETE
    input: ResultResponse


class NewImageFilesInvocation(InvocationBase):
    """Sent when new image files were imported, so the app can decide whether to analyse.

    Ignoring the call is a valid response -- no result needs to be stored.
    """

    action: Literal[Action.NEW_IMAGE_FILES] = Action.NEW_IMAGE_FILES
    cancellationToken: str
    # ponytail: Sectra always sends {"type": "wholeSlide"} here, purely for symmetry with
    # the create action. Kept (rather than dropped via extra="ignore") so model_dump()
    # stays wire-faithful, since MockSectraServer serialises invocations that way.
    input: CreateInput = WholeSlideInput()
    imageInfo: ImageMetadata


Invocation = Annotated[
    CreateInvocation | ModifyInvocation | CancelInvocation | DeleteInvocation | NewImageFilesInvocation,
    Field(discriminator="action"),
]
