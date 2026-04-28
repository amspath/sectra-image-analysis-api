# Sectra Image Analysis API

A Python client library for building AI applications on [Sectra PACS](https://sectra.com/medical/product-area/digital-pathology/), targeting digital pathology workflows. It handles authentication, image metadata retrieval, WSI file downloads, and result submission — plus a mock server for local development. 

## Version
The library currently supports functionality up to do version 3.4 (Dec 2023). However, we will update to 5.0 in Juli, after which this library will be adjusted to the newest version as well. 

## Installation

```bash
pip install sectra-image-analysis-api
```

Requires Python 3.11+.

## At a glance

| Component | Purpose |
|---|---|
| [`SectraClient`](api/client.md) | Talk to a live Sectra PACS instance |
| [`MockSectraServer`](api/mock-server.md) | Simulate Sectra locally for development and testing |
| [Schemas](api/schemas.md) | Pydantic models for invocations, results, and image metadata |

## How it works

Sectra sends an **invocation** (HTTP POST) to your application's webhook when analysis is requested. Your app uses `SectraClient` to fetch image data, run its analysis, and post results back to Sectra.

```
Sectra PACS ──POST /your/hook──► Your App
                                    │
                          SectraClient.get_image_metadata()
                          SectraClient.download_slide_files()
                                    │
                          SectraClient.create_results()
                                    │
Your App ───── result ────────────► Sectra PACS
```

See the [Quick Start](quickstart.md) to get running.
