from sectra_client import SectraClient
from sectra_client.schemas import AdaptedResult, DisplayProperties, Style
from sectra_client.schemas.results import PrimitiveResultContent, ResultResponse

callback_url = "..."
token = "..."
app_id = "..."
slide_id = "..."

with SectraClient(url=callback_url, token=token) as client:
    results = client.get_all_results(wsi_id=slide_id, app_id=app_id)

result: ResultResponse = results[0]

# Result data is a union of PrimitiveResultContent and PatchResultContent, so we need to assert the type.
assert isinstance(result.data.result, PrimitiveResultContent)
print(result.data.result.content[0])

new_result = AdaptedResult(
    slideId=slide_id,
    displayResult="Analysis failed",
    applicationVersion="0.0.1",
    versionId="2",
    data=result.data,
    displayProperties=DisplayProperties({"Status": "Failed", "Confidence": "0%"}),
)

assert isinstance(new_result.data.result, PrimitiveResultContent)
new_result.data.result.content[0].style = Style(strokeStyle="#00FF00", size=10, fillStyle="#00FFFF")

with SectraClient(url=callback_url, token=token) as client:
    client.update_results(app_id=app_id, result_id=result.id, result=new_result)
