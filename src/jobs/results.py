
import json
from fastapi import Response

def to_response(result, task_id = None):
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


def to_error_response(msg, status_code=400):
    """
    Create a JSON error response for a request that can't be processed.

    :param msg: The error message
    :param status_code: The HTTP status code
    :return: A response
    """
    return Response(
        content=json.dumps({"state": "FAILURE", "msg": msg}),
        status_code=status_code,
        media_type="application/json"
    )
