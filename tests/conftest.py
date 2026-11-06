import os
import tempfile

# The app creates folders and loads users when it is imported, so configure it before the import.
_folder = tempfile.mkdtemp()
os.environ['DATABOARD_USERFILE'] = os.path.join(_folder, 'users', 'users.json')
os.environ['DATABOARD_JOBS_FOLDER'] = os.path.join(_folder, 'jobs')

import pytest
from fastapi.testclient import TestClient

from src import app as appModule
from src.jobs import worker
from src.users import users


def _makeClient(eager):
    worker.celery.conf.update(
        broker_url='memory://',
        result_backend='cache+memory://',
        task_always_eager=eager,
        task_store_eager_result=True,
    )
    testUser = users.User(username='tester', password='x', disabled=False)
    appModule.app.dependency_overrides[appModule.get_current_user] = lambda: testUser
    appModule.app.dependency_overrides[appModule.enforce_user_rate_limit] = lambda: None

    return TestClient(appModule.app)


@pytest.fixture
def client():
    """
    A client for the HTTP endpoints.

    Celery runs the tasks eagerly with in-memory broker and backend,
    so no RabbitMQ is needed and tasks are finished when the request returns.
    Authorization and rate limits are switched off.
    """
    yield _makeClient(eager=True)
    appModule.app.dependency_overrides.clear()


@pytest.fixture
def pendingClient():
    """
    Like client, but nothing consumes the tasks, so they stay pending.
    Use worker.celery.backend.store_result() to finish single tasks by hand.
    """
    yield _makeClient(eager=False)
    appModule.app.dependency_overrides.clear()
