from fastapi import Response


def avatar_response(content: bytes, content_type: str) -> Response:
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
