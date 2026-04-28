# uvicorn minimal_server:app --port 19013

import random

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sectra_client.client import SectraClient
from sectra_client.schemas import (
    CreateInvocation,
    Invocation,
    ModifyInvocation,
    Patch,
    PatchContent,
    PatchResultContent,
    Point,
    Polygon,
    PrimitiveResultContent,
    Result,
    ResultData,
    ResultType,
    Status,
)
from sectra_client.schemas.results import Action, AdaptedResult, ResultResponse

TAGS = ["Uncertain", "Not tumor", "Possible tumor", "Probable tumor", "Tumor"]

app = FastAPI(title="Root App")
raid_app = FastAPI(title="RAID API")


def build_patch_result(n_patches: int = 10) -> PatchResultContent:
    patches = []
    all_points = []

    for _ in range(n_patches):
        cx, cy = random.uniform(0.1, 0.9), random.uniform(0.1, 0.9)
        patches.append(
            Patch(
                tag=random.randint(0, 4),
                position=Point(x=cx, y=cy),
                sortKeyValue=0.0,
            )
        )
        all_points.append(Point(x=cx, y=cy))

    xs = [p.x for p in all_points]
    ys = [p.y for p in all_points]
    padding = 0.01
    bounding_polygon = Polygon(
        points=[
            Point(x=min(xs) - padding, y=min(ys) - padding),
            Point(x=max(xs) + padding, y=min(ys) - padding),
            Point(x=max(xs) + padding, y=max(ys) + padding),
            Point(x=min(xs) - padding, y=max(ys) + padding),
        ]
    )

    return PatchResultContent(
        type=ResultType.PATCHES,
        content=PatchContent(
            description="Random patch demo.",
            polygons=[bounding_polygon],
            patches=patches,
            tags=TAGS,
            actions=[Action(id="addpatch", state=0, name="Add Patch", tooltip="Add a new patch")],
            patchSize=128,
            magnification=2.0,
            statuses={"allowVerify": Status(value=True, message="Ready for review")},
        ),
    )


def _handle_create(invocation: CreateInvocation, sectra_client: SectraClient) -> ResultResponse:
    result_content = build_patch_result(n_patches=10)
    return sectra_client.create_results(
        invocation.applicationId,
        Result(
            slideId=invocation.slideId,
            displayResult=f"{len(result_content.content.patches)} patches",
            applicationVersion="1.0",
            data=ResultData(result=result_content),
        ),
    )


def _handle_modify(invocation: ModifyInvocation, sectra_client: SectraClient) -> Result:
    return sectra_client.update_results(
        app_id=invocation.applicationId,
        result_id=invocation.input.id,
        result=AdaptedResult(
            slideId=invocation.slideId,
            displayResult=invocation.input.displayResult,
            applicationVersion=invocation.input.applicationVersion,
            attachments=invocation.input.attachments,
            data=invocation.input.data,
            displayProperties=invocation.input.displayProperties,
            versionId=invocation.input.versionId,
        ),
    )


@raid_app.post("/sectra/hook")
async def sectra_hook(invocation: Invocation):
    callback = invocation.callbackInfo
    with SectraClient(callback.url, callback.token) as sectra_client:
        match invocation:
            case CreateInvocation():
                result = _handle_create(invocation, sectra_client)
            case ModifyInvocation():
                result = _handle_modify(invocation, sectra_client)
            case _:
                result = Result(
                    slideId=invocation.slideId,
                    displayResult="",
                    applicationVersion="1.0",
                    data=ResultData(result=PrimitiveResultContent(content=[])),
                )
        return JSONResponse(content=result.model_dump(), headers=sectra_client.response_headers)


app.mount("/raid", raid_app)
