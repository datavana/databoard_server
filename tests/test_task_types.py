from src.jobs import worker


# An unknown task type answers 400 and names the type, because it is a mistake of the client and not a server fault.
def test_unknown_task_type_answers_400_naming_the_type(client):
    response = client.post('/tasks/run', json={'task': 'dance', 'input': ['a']})

    assert response.status_code == 400
    body = response.json()
    assert body['state'] == 'FAILURE'
    assert "'dance'" in body['msg']


# Known LLM task types are still accepted, so the change does not break existing clients.
def test_known_task_type_is_still_accepted(client, monkeypatch):
    class FakeTask:
        id = 'fake-id'

    async def fakeStatus(taskId, wait=0):
        return {'state': 'PENDING', 'task_id': taskId}

    for name in ('summarize', 'coding', 'annotate', 'triples'):
        monkeypatch.setattr(getattr(worker, name), 'delay', lambda data, options: FakeTask())
    monkeypatch.setattr(worker, 'getStatus', fakeStatus)

    for name in ('summarize', 'coding', 'annotate', 'triples'):
        response = client.post('/tasks/run', json={'task': name, 'input': ['a']})
        assert response.status_code == 202, name


# Unexpected errors still answer 500 without a message, so internal details do not leak.
def test_unexpected_errors_do_not_leak_messages(client, monkeypatch):
    def explode(data, options):
        raise RuntimeError('secret internal detail')

    monkeypatch.setattr(worker.summarize, 'delay', explode)

    response = client.post('/tasks/run', json={'task': 'summarize', 'input': ['a']})

    assert response.status_code == 500
    assert 'secret' not in response.text
