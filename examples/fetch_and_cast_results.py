from sectra_client import SectraClient
from sectra_client.schemas.results import PatchResultContent, PrimitiveResultContent, ResultResponse

callback_url = "..."
token = "..."
app_id = "..."
slide_id = "..."

with SectraClient(url=callback_url, token=token) as client:
    results = client.get_all_results(wsi_id=slide_id, app_id=app_id)

result: ResultResponse = results[0]

# Result data is a union of PrimitiveResultContent and PatchResultContent, so we need to assert the type.
if isinstance(result.data.result, PrimitiveResultContent):
    print(result.data.result.content[0])
if isinstance(result.data.result, PatchResultContent):
    raise NotImplementedError("PatchResultContent not implemented in this test")
