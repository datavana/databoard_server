import pytest

from databoard_core.clients import ParserClient, register_parser, unregister_parser
from src.jobs import worker


class StubParserClient(ParserClient):
    """
    Placeholder parser. The input decides the answer:
    'warn' reports a warning, 'bad' an error, 'boom' raises an exception, anything else is clean.
    """
    def answer(self, content):
        if content == 'boom':
            raise RuntimeError('parser crashed')
        level = {'warn': 'warning', 'bad': 'error'}.get(content)
        errors = [self.makeError(level, 1, 1, 1, 'msg')] if level else []
        return {'xml': f'<stub>{content}</stub>', 'errors': errors}


@pytest.fixture(autouse=True)
def stubParser():
    register_parser('stub', 'test', StubParserClient)
    yield
    unregister_parser('stub', 'test')


OPTIONS = {'formalism': 'stub', 'dialect': 'test'}


def submit(client, inputs):
    response = client.post('/tasks/run', json={'task': 'parse', 'input': inputs, 'options': OPTIONS})
    return response.json()['task_id']


def finishTask(batchId, index, result):
    """Store the result of one task of a batch, as a worker would do."""
    from celery.result import GroupResult
    task = GroupResult.restore(batchId, app=worker.celery).results[index]
    worker.celery.backend.store_result(task.id, result, 'SUCCESS')


# The batch id from the POST can be queried and is not stuck in PENDING, because a group id is not a single task id.
def test_batch_id_can_be_queried(client):
    batchId = submit(client, ['a', 'b'])

    response = client.get(f'/tasks/run/{batchId}')

    assert response.status_code == 200
    assert response.json()['state'] == 'SUCCESS'
    assert response.json()['task_id'] == batchId


# The result is a list in input order with a state and the parse result per entry, so clients match results to inputs by position.
def test_result_is_a_list_in_input_order(client):
    batchId = submit(client, ['first', 'second', 'third'])

    entries = client.get(f'/tasks/run/{batchId}').json()['result']

    assert [e['result']['xml'] for e in entries] == [
        '<stub>first</stub>', '<stub>second</stub>', '<stub>third</stub>'
    ]
    assert all(e['state'] == 'SUCCESS' for e in entries)


# While some inputs are pending, finished entries are already included, so clients can follow the progress of a large batch.
def test_finished_entries_are_included_while_the_batch_is_pending(pendingClient):
    batchId = submit(pendingClient, ['a', 'b', 'c'])
    finishTask(batchId, 1, {'xml': '<done/>', 'errors': [], 'failed': False})

    response = pendingClient.get(f'/tasks/run/{batchId}')

    assert response.status_code == 202
    assert response.headers['Location'] == f'/tasks/run/{batchId}'
    body = response.json()
    assert body['state'] == 'PENDING'
    assert [e['state'] for e in body['result']] == ['PENDING', 'SUCCESS', 'PENDING']
    assert body['result'][1]['result']['xml'] == '<done/>'


# A batch stays PENDING until every input is finished, even if most are done.
def test_batch_is_pending_while_any_input_is_pending(pendingClient):
    batchId = submit(pendingClient, ['a', 'b'])
    finishTask(batchId, 0, {'xml': '<done/>', 'errors': [], 'failed': False})

    assert pendingClient.get(f'/tasks/run/{batchId}').json()['state'] == 'PENDING'


# Warnings do not fail an input, so a batch with only warnings is a SUCCESS.
def test_warnings_do_not_fail_the_batch(client):
    body = client.get(f'/tasks/run/{submit(client, ["ok", "warn"])}').json()

    assert body['state'] == 'SUCCESS'
    assert body['result'][1]['result']['errors'][0]['level'] == 'warning'


# Some failed inputs make the batch MIXED and answer 200, because it still contains usable results.
def test_some_failed_inputs_make_the_batch_mixed(client):
    response = client.get(f'/tasks/run/{submit(client, ["ok", "bad", "ok"])}')

    assert response.status_code == 200
    body = response.json()
    assert body['state'] == 'MIXED'
    assert [e['state'] for e in body['result']] == ['SUCCESS', 'FAILURE', 'SUCCESS']
    assert body['result'][1]['result']['xml'] == '<stub>bad</stub>'


# All failed inputs make the batch FAILURE, consistent with the LLM tasks.
def test_all_failed_inputs_make_the_batch_failure(client):
    response = client.get(f'/tasks/run/{submit(client, ["bad", "bad"])}')

    assert response.status_code == 500
    assert response.json()['state'] == 'FAILURE'


# A task that crashes fails only its own entry, so one broken input does not hide the others.
def test_crashed_task_fails_only_its_entry(client):
    body = client.get(f'/tasks/run/{submit(client, ["ok", "boom"])}').json()

    assert body['state'] == 'MIXED'
    assert body['result'][0]['state'] == 'SUCCESS'
    assert body['result'][1]['state'] == 'FAILURE'
    assert 'parser crashed' in body['result'][1]['msg']


# Posting with wait returns the finished batch directly, like the LLM tasks do.
def test_post_returns_finished_results_when_tasks_are_done(client):
    response = client.post('/tasks/run', json={'task': 'parse', 'input': ['a'], 'options': OPTIONS})

    assert response.status_code == 200
    assert response.json()['result'][0]['result']['xml'] == '<stub>a</stub>'


# Querying a single task id is unchanged: the result is the task result, not a list.
def test_single_task_lookup_is_unchanged(client):
    worker.celery.backend.store_result('single-task-id', {'answers': [{'llm_result': 'x'}]}, 'SUCCESS')

    response = client.get('/tasks/run/single-task-id')

    assert response.status_code == 200
    assert response.json() == {
        'state': 'SUCCESS',
        'task_id': 'single-task-id',
        'result': {'answers': [{'llm_result': 'x'}]}
    }


# An unknown id is still pending, unchanged from before.
def test_unknown_id_is_pending(client):
    response = client.get('/tasks/run/unknown-id')

    assert response.status_code == 202
    assert response.json() == {'state': 'PENDING', 'task_id': 'unknown-id'}
