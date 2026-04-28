from enum import Enum, unique
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, Field

from sectra_client.schemas.common import Point, Polygon


class Style(BaseModel):
    strokeStyle: str | None = None
    fillStyle: str | None = None
    size: int | None = None


class Polyline(BaseModel):
    points: list[Point]


class Label(BaseModel):
    location: Point
    label: str


class PrimitiveItem(BaseModel):
    style: Style | None = None
    polygons: list[Polygon] = Field(default_factory=list)
    polylines: list[Polyline] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)


class Patch(BaseModel):
    tag: int
    position: Point
    sortKeyValue: float

class Action(BaseModel):
    id: str
    state: int
    name: str
    tooltip: str

class Status(BaseModel):
    value: bool | None = True
    message: str | None = None


class PatchContent(BaseModel):
    description: str
    polygons: list[Polygon]
    patches: list[Patch]
    actions: list[Action]
    tags: list[str]
    patchSize: int
    magnification: float
    statuses: dict[str, Status] = Field(default_factory=lambda: {"allowVerify": Status()})


@unique
class ResultType(str, Enum):
    PATCHES = "patchCollection"
    PRIMITIVES = "primitive"


class PrimitiveResultContent(BaseModel):
    type: Literal[ResultType.PRIMITIVES] = ResultType.PRIMITIVES
    content: list[PrimitiveItem]


class PatchResultContent(BaseModel):
    type: Literal[ResultType.PATCHES] = ResultType.PATCHES
    content: PatchContent


ResultContent = Annotated[PrimitiveResultContent | PatchResultContent, Field(discriminator="type")]

DisplayProperties: TypeAlias = dict[str, str | int | float]


class ResultData(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    result: ResultContent


@unique
class AttachmentState(str, Enum):
    NEW = "new"
    UPLOAD_IN_PROGRESS = "upload-in-progress"
    STORED = "stored"


class Attachment(BaseModel):
    name: str
    state: AttachmentState


class Result(BaseModel):
    slideId: str
    displayResult: str
    applicationVersion: str
    attachments: list[Attachment] = Field(default_factory=list)
    data: ResultData = Field(default_factory=ResultData)
    displayProperties: DisplayProperties = Field(default_factory=dict)


class AdaptedResult(Result):
    versionId: str


class ResultResponse(Result):
    id: int
    versionId: str
