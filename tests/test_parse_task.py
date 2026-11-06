import pytest
from celery.result import GroupResult

from databoard_core.clients import ParserClient, register_parser, unregister_parser
from src.jobs import worker


class StubParserClient(ParserClient):
    """Placeholder parser: answers with fixed XML derived from the input."""
    def answer(self, content):
        return {'xml': f'<stub>{content}</stub>', 'errors': []}


@pytest.fixture(autouse=True)
def stubParser():
    register_parser('stub', 'test', StubParserClient)
    yield
    unregister_parser('stub', 'test')


def postParse(client, input, options=None):
    options = {'formalism': 'stub', 'dialect': 'test'} if options is None else options
    return client.post('/tasks/run', json={'task': 'parse', 'input': input, 'options': options})


def restoreBatch(batchId):
    return GroupResult.restore(batchId, app=worker.celery)


# A list of inputs is accepted with 202, one id and a Location to that id, so the client sees a single batch and not a list of task ids.
def test_list_of_inputs_returns_202_with_one_id_and_location(client):
    response = postParse(client, ['a', 'b', 'c'])

    assert response.status_code == 202
    body = response.json()
    assert body['state'] == 'PENDING'
    assert response.headers['Location'] == '/tasks/run/' + body['task_id']


# One Celery task is started per input, bundled as a group, so the work can be spread across workers.
def test_each_input_becomes_one_task_in_one_group(client):
    batchId = postParse(client, ['a', 'b', 'c']).json()['task_id']

    batch = restoreBatch(batchId)
    assert len(batch.results) == 3


# The tasks run the parse workflow for their own input and keep the input order, so results can later be matched by position.
def test_tasks_parse_their_input_in_input_order(client):
    batchId = postParse(client, ['first', 'second', 'third']).json()['task_id']

    results = [task.get() for task in restoreBatch(batchId).results]
    assert [r['xml'] for r in results] == [
        '<stub>first</stub>', '<stub>second</stub>', '<stub>third</stub>'
    ]
    assert all(r['failed'] is False for r in results)


# A single string runs as a group of one, so the response always has the same shape.
def test_single_string_runs_as_group_of_one(client):
    response = postParse(client, 'only')

    assert response.status_code == 202
    batch = restoreBatch(response.json()['task_id'])
    assert len(batch.results) == 1
    assert batch.results[0].get()['xml'] == '<stub>only</stub>'


# rules are accepted, so clients can already send them before they are processed.
def test_rules_are_accepted(client):
    response = postParse(client, ['a'], {'formalism': 'stub', 'dialect': 'test', 'rules': {'x': 1}})

    assert response.status_code == 202


# A missing formalism answers 400 with a message naming the field, so a client notices its mistake at once.
def test_missing_formalism_answers_400(client):
    response = postParse(client, ['a'], {'dialect': 'test'})

    assert response.status_code == 400
    assert 'formalism' in response.json()['msg']


# A missing dialect answers 400, so a text is never silently parsed with a default Dialect.
def test_missing_dialect_answers_400(client):
    response = postParse(client, ['a'], {'formalism': 'stub'})

    assert response.status_code == 400
    assert 'dialect' in response.json()['msg']


# Missing options altogether answer 400 as well.
def test_missing_options_answer_400(client):
    response = postParse(client, ['a'], {})

    assert response.status_code == 400


# A pair without a parser answers 400 and names the pair, so users see which combination is not supported.
def test_unknown_pair_answers_400_naming_the_pair(client):
    response = postParse(client, ['a'], {'formalism': 'ebnf', 'dialect': 'isodate'})

    assert response.status_code == 400
    assert "'ebnf'" in response.json()['msg'] and "'isodate'" in response.json()['msg']


# Options that are not strings answer 400 instead of crashing the server.
def test_non_string_option_answers_400(client):
    response = postParse(client, ['a'], {'formalism': ['stub'], 'dialect': 'test'})

    assert response.status_code == 400


# An empty input list answers 400, because there is nothing to parse and an empty batch would have no meaningful state.
def test_empty_input_answers_400(client):
    response = postParse(client, [])

    assert response.status_code == 400


# A rejected request starts no task at all, so invalid requests do not use up worker capacity.
def test_rejected_request_starts_no_task(client, monkeypatch):
    started = []
    monkeypatch.setattr(worker.parse, 'apply_async', lambda *a, **k: started.append(1))
    monkeypatch.setattr(worker.parse, 's', lambda *a, **k: started.append(1))

    postParse(client, ['a'], {'formalism': 'ebnf', 'dialect': 'isodate'})

    assert started == []


# LLM tasks are unchanged: they still start one task for the whole input and return its status.
def test_llm_tasks_are_unchanged(client, monkeypatch):
    calls = []

    class FakeTask:
        id = 'fake-id'

    async def fakeStatus(taskId, wait=0):
        return {'state': 'PENDING', 'task_id': taskId}

    monkeypatch.setattr(worker.summarize, 'delay', lambda data, options: calls.append((data, options)) or FakeTask())
    monkeypatch.setattr(worker, 'getStatus', fakeStatus)

    response = client.post('/tasks/run', json={'task': 'summarize', 'input': ['text'], 'options': {'x': 1}})

    assert calls == [(['text'], {'x': 1})]
    assert response.status_code == 202
    assert response.json() == {'state': 'PENDING', 'task_id': 'fake-id'}
