from typing import Annotated, List, Optional
from fastapi import FastAPI, Depends, Request, HTTPException, Response, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import urllib.parse

from pydantic import conint

import json

from .jobs import worker, payloads
from .users import users

app = FastAPI()

# Authorization
accounts = users.Accounts()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    user = accounts.getCurrentUser(token)
    if user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

def require_admin(user: Annotated[users.User, Depends(get_current_user)]):
    if user.usertype != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

# Serve static files (CSS, JS, etc.)
app.mount("/static", StaticFiles(directory="src/static"), name="static")

# Set up templates directory
templates = Jinja2Templates(directory="src/templates")

# Will hold our Llm client
myLlmClient = None

# Custom Exception Handler for HTTPException
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Renders an HTML error page instead of JSON response for HTTP exceptions."""

    if request.url.path == "/login":
        return RedirectResponse(url="/login?success=0", status_code=303)

    return templates.TemplateResponse(
        "error.html",
        {"request": request, "exc": exc, "title": "Databoard"},
        status_code=exc.status_code
    )

@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_form(request: Request, success: str = Query(False)):
    """Serves a simple HTML login form."""
    template_name = "success.html" if success == "1" else "login.html"
    return templates.TemplateResponse(template_name, {"request": request, "success": success, "title": "Databoard"})

@app.post("/login", include_in_schema=False)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """Handles login and redirects with token in the hash fragment."""
    access_token = accounts.getAccessToken(form_data)
    redirect_url = f"/login?success=1#access_token={access_token.access_token}"
    return RedirectResponse(url=redirect_url, status_code=303)


@app.get("/", include_in_schema=False)
async def homepage(request: Request):
    # try:
    #     taskcount = await worker.getQueueLength()
    # except Exception as e:
    #     taskcount = None
    taskcount = None
    return templates.TemplateResponse("home.html", {"request": request, "title": "Databoard", "taskcount" : taskcount})

@app.post("/tasks/run")
async def task_add(
        user: Annotated[users.User, Depends(get_current_user)],
        request: Request,
        payload: payloads.TaskInput,
        wait: conint(ge=0, le=10) = 0
):
    """
    Generate a task

    Post a JSON document with the following keys to create a task:
    - task: The task type, one of 'summarize', 'coding', 'annotate' or 'triples'.
    - input: The input text as a string or a list of strings.
    - options: Additional configuration (optional).

    The summarize task understands the following options keys:
    - rules: For the multi summarize mode, the codebook with selection rules.
             An array of dicts with the keys category, description, and optionally example.
             Each description should prompt the selection of specific text passages that will be summarized.
             The workflow can be used for open coding tasks.
    - mode: 'single' to output a single value (default),
            'multi' to output a value for each category.

    The coding task understands the following options keys:
    - rules: The codebook, an array of dicts with the keys category, description, and example
    - mode: 'single' to decide for one category for each case (default),
            'multi' to output a decision for each category.

    The annotate tasks needs a rule book in the options:
    - rules An array of dicts with the keys category, description, and example.
            The description is used to identify text segments.
            The example should contain comma separated text segments that match the rule.
            The category will be used as value attribute in the annotation.

    The following options are supported for all task types:
    - model: The model to use, overrides the server default.
             Candidates are: 'Llama-3.3-70B' (default), 'mistral-small',
                             'gemma-3-27b-it', 'gemma-3',
                             'gpt-oss-120b', 'Apertus-8B-Instruct-2509'.
    - temperature: The temperature to use (overrides the server default which is NOT_GIVEN).
    - raw: If true, returns the raw LLM output and by passes all task post-processing (default: false).

    Prompts:
    In the options, you can optionally define a custom prompt template name in the `prompts` key.
    The  prompt template files matching the name must be available on the server.
    Alternatively, provide an object with the prompt text in the `user` and `system` values.
    The templates support the following keys in double curly bracket placeholders

    - `{{text}}`: Will be replaced by the input value.
    - `{{rules}}`: Will be replaced by the prepared codebook, annotation or summary rules.
                   The databoard automatically prepares a markdown text representation of the rules.

   Example for a coding task:
    ```
    {
      "task": "coding",
      "input": ["How is it going?", "Hello", "Sure!"],

      "options": {
          "rules": [
              {"category":"A","description":"A question", "example":"Why?"},
              {"category":"B","description":"An answer", "example":"Yes!"}
          ],
          "mode": "multi"
      }
    }
    ```

    After posting a task, use the tasks/run/{taks_id} endpoint to get status
    updates and the result.

    Optionally, for quick tasks, set the query parameter `wait` to a number of seconds.
    When creating the task, it will directly check the result for this timespan and,
    if possible, return the result with the response.

    :param user:
    :param request:
    :param payload:
    :param wait Maximum seconds to wait for the task to be finished.
    :return:
    """
    # TODO: put user.username in the task data

    if payload.task == 'summarize':
        task = worker.summarize.delay(payload.input, payload.options)
    elif payload.task == 'coding':
        task = worker.coding.delay(payload.input, payload.options)
    elif payload.task == 'triples':
        task = worker.triples.delay(payload.input, payload.options)
    elif payload.task == 'annotate':
        task = worker.annotate.delay(payload.input, payload.options)
    else:
        raise ValueError("Unsupported task type")

    result = await worker.getStatus(task.id, wait)

    if result.get("state") == "PENDING":
        response = Response(
            content=json.dumps(result),
            status_code=202,
            media_type="application/json"
        )
        response.headers["Location"] = f"/tasks/run/{task.id}"
        response.headers["Retry-After"] = "10"
        return response

    elif result.get("state") == "FAILURE":
        return result, 500

    return result

@app.get("/tasks/run/{task_id}")
async def task_status(
    user: Annotated[users.User, Depends(get_current_user)],
    task_id: str,
    wait: conint(ge=0, le=10) = 0
):
    """
    Get the task status and if finished the result

    :param user:
    :param task_id:
    :param wait Maximum seconds to wait for the task to be finished.
    :return:
    """
    # TODO: Check user.username in the task data

    result = await worker.getStatus(task_id, wait)

    if result.get("state") == "PENDING":
        response = Response(
            content=json.dumps(result),
            status_code=202,
            media_type="application/json"
        )
        response.headers["Location"] = f"/tasks/run/{task_id}"
        response.headers["Retry-After"] = "10"
        return response

    elif result.get("state") == "FAILURE":
        return result, 500

    return result


@app.post("/token")
async def token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> users.Token:
    """
    Login endpoint to get an access token
    (for use in the the Swagger UI)

    :param form_data:
    :return:
    """
    return accounts.getAccessToken(form_data)


@app.get("/users", response_model=List[users.PublicUser])
async def users_list(
    admin: Annotated[users.User, Depends(require_admin)]
):
    """
    List all users (admin permissions required).
    """
    return [users.PublicUser(**u) for u in accounts.accounts.values()]


@app.post("/users/add", response_model=users.PublicUser)
async def users_add(
    admin: Annotated[users.User, Depends(require_admin)],
    username: str = Body(...),
    password: str = Body(...),
    email: Optional[str] = Body(None),
    fullname: Optional[str] = Body(None),
    usertype: str = Body("human"),
    tokenExpires: bool = Body(True)
):
    """
    Add a user (admin permissions required).

    :param admin:
    :param username:
    :param password:
    :param email:
    :param fullname:
    :param usertype:
    :param tokenExpires:
    :return:
    """
    return accounts.addUser(
        username=username,
        password=password,
        email=email,
        fullname=fullname,
        usertype=usertype,
        tokenExpires=tokenExpires
    )

@app.post("/users/disable/{username}", response_model=users.PublicUser)
async def users_disable(username: str, admin: Annotated[users.User, Depends(require_admin)]):
    """
    Disable a user account  (admin permissions required).
    :param username:
    :param admin:
    :return:
    """
    return accounts.disableUser(username)

@app.delete("/users/delete/{username}")
async def users_delete(
    username: str,
    admin: Annotated[users.User, Depends(require_admin)]
):
    """
    Delete a user account  (admin permissions required).
    """
    return accounts.deleteUser(username)


# @app.get("/hash/{secret}")
# async def get_hash(secret):
#     return accounts.hashPassword(secret)

