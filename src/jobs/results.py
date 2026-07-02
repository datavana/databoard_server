
import json
from fastapi import Response

def to_response(result, task_id):
    if result.get("state") == "PENDING":
        response = Response(
            content=json.dumps(result),
            status_code=202,
            media_type="application/json"
        )
        response.headers["Location"] = f"/tasks/run/{task_id}"
        response.headers["Retry-After"] = "10"

    elif result.get("state") == "FAILURE":
        response = Response(
            content=json.dumps(result),
            status_code=500,
            media_type="application/json"
        )

    else:
        response = Response(
            content=json.dumps(result),
            status_code=200,
            media_type="application/json"
        )

    return response
