from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from sectra_client.client import SectraClient
from sectra_client.schemas import Point, Polygon, PrimitiveItem, Result, ResultData, Style
from sectra_client.schemas.invocation import Invocation
from sectra_client.schemas.results import PrimitiveResultContent

# This is the main ASGI app
app = FastAPI(title="Root App")

# This is the RAID sub-application
raid_app = FastAPI(title="RAID API")


@raid_app.post("/sectra/hook")
async def sectra_hook(invocation: Invocation, raw_request: Request):
    # Show complete request
    body = await raw_request.json()
    print(body)

    # Create a result square result to send back
    result_payload = Result(
        slideId=invocation.slideId,
        displayResult="Example Result",
        applicationVersion="0.0.1",
        data=ResultData(
            result=PrimitiveResultContent(
                content=[
                    PrimitiveItem(
                        polygons=[
                            Polygon(
                                points=[
                                    Point(x=0.0, y=0.0),
                                    Point(x=1.0, y=0.0),
                                    Point(x=1.0, y=1.0),
                                    Point(x=0.0, y=1.0),
                                ]
                            )
                        ],
                        polylines=[],
                        labels=[],
                        style=Style(strokeStyle="#FF0000", size=2),
                    )
                ]
            )
        ),
    )

    # Upload a permanent result to Sectra using the callback URL and token provided in the invocation
    with SectraClient(url=invocation.callbackInfo.url, token=invocation.callbackInfo.token) as client:
        client.create_results(app_id=invocation.applicationId, results=result_payload)

    # Sectra also expects a response to the hook request. Otherwise it will show an error to the user.
    empty_temp_result = Result(
        slideId=invocation.slideId,
        displayResult="",
        applicationVersion="0.0.1",
        data=ResultData(result=PrimitiveResultContent(content=[])),
    )

    return JSONResponse(empty_temp_result.model_dump())


# Mount RAID app under /raid
app.mount("/raid", raid_app)
