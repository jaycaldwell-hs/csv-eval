## Vertex Access Notes

Current project:
- `handshake-production`

Auth:
```bash
gcloud auth login --update-adc
```

## Gemini on Vertex

Current verifier default:
- model: `gemini-3-pro-preview`
- location: `global`

Minimal example:

```python
from google import genai
from google.genai import types


def generate() -> None:
    client = genai.Client(
        vertexai=True,
        project="handshake-production",
        location="global",
    )

    response = client.models.generate_content(
        model="gemini-3-pro-preview",
        contents="howdy!",
        config=types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=1024,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
            thinking_config=types.ThinkingConfig(
                include_thoughts=False
            ),
        ),
    )

    texts = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            text = getattr(part, "text", None)
            if text:
                texts.append(text)

    print("\n".join(texts).strip())


if __name__ == "__main__":
    generate()
```

Notes:
- The SDK may emit warnings if you access `response.text` when non-text parts exist.
- Reading `candidate.content.parts[*].text` is cleaner for current Gemini responses.

## Claude on Vertex

Known-good versioned model example:
- model: `claude-sonnet-4-5@20250929`
- region: `us-east5`

Minimal example:

```python
from anthropic import AnthropicVertex


def generate() -> None:
    client = AnthropicVertex(
        region="us-east5",
        project_id="handshake-production",
    )

    with client.messages.stream(
        model="claude-sonnet-4-5@20250929",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": "howdy!",
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)

    print()


if __name__ == "__main__":
    generate()
```




