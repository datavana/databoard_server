import os

import numpy as np
#from kombu import Connection, Queue
import asyncio

from celery import Celery, Task, group
from celery.result import AsyncResult, GroupResult
from celery.app import trace

from databoard_core.flows import CodingWorkflow
from databoard_core.flows import SummaryWorkflow
from databoard_core.flows import AnnoWorkflow
from databoard_core.flows import TripleWorkflow
from databoard_core.flows import ParseWorkflow
from databoard_core.clients import has_parser

# Remove data from log
trace.LOG_SUCCESS = """\
Task %(name)s[%(id)s] succeeded in %(runtime)ss\
"""

# Start Celery
jobsFolder = os.getenv('DATABOARD_JOBS_FOLDER', '/app/data/.jobs')
os.makedirs(jobsFolder, exist_ok=True)
brokerHost = os.getenv('RABBITMQ_HOST', 'rabbitmq')
brokerUrl = 'amqp://guest:guest@' + brokerHost
celery = Celery(
    'tasks',
    broker=brokerUrl,
    backend='file://' + jobsFolder
)

async def getQueueLength():
    i = celery.control.inspect()
    scheduled = i.scheduled() or {}
    active = i.active() or {}
    #reserved = i.reserved() or {}

    scheduled_count = sum(len(tasks) for tasks in scheduled.values())
    active_count = sum(len(tasks) for tasks in active.values())
    #reserved_count = sum(len(tasks) for tasks in reserved.values())

    return scheduled_count + active_count


def _is_non_empty(value):
    if value is None:
        return False
    if isinstance(value, float) and np.isnan(value):
        return False
    if isinstance(value, str):
        return value.strip() != ''
    return True


def _derive_result_state(task_state, task_info):
    """
    Check the answers. A llm_status field indicates errors.
    In this case, revise the task result state.

    :param task_state:
    :param task_info:
    :return:
    """
    if task_state != 'SUCCESS' or not isinstance(task_info, dict):
        return task_state

    answers = task_info.get('answers')
    if not isinstance(answers, list) or len(answers) == 0:
        return task_state

    llm_status = [row.get('llm_status') if isinstance(row, dict) else None for row in answers]
    non_empty_count = sum(1 for value in llm_status if _is_non_empty(value))

    if non_empty_count == len(llm_status):
        return 'FAILURE'
    if non_empty_count > 0:
        return 'MIXED'

    return task_state


def _derive_entry(task):
    """
    Get the state and result of a single task of a batch.

    :param task: An AsyncResult
    :return: A dict with the state and, if the task is finished, the result or an error message.
    """
    if not task.ready():
        return {"state": "PENDING"}

    info = task.info
    if isinstance(info, dict):
        # An input with error or fatal entries counts as failed
        return {"state": "FAILURE" if info.get('failed') else "SUCCESS", "result": info}

    entry = {"state": "FAILURE"}
    if isinstance(info, Exception):
        entry["msg"] = str(info)
    return entry


def _derive_batch_state(entries):
    """
    Derive the overall state of a batch from the states of its entries.

    :param entries: A list of entries with a state
    :return: PENDING while any entry is pending, then SUCCESS, MIXED or FAILURE
    """
    states = [entry["state"] for entry in entries]
    if "PENDING" in states:
        return "PENDING"

    failed = states.count("FAILURE")
    if failed == 0:
        return "SUCCESS"
    if failed == len(states):
        return "FAILURE"
    return "MIXED"


async def getBatchStatus(batch, wait=0):
    """
    Get the status of a batch of tasks (a group), see submitParse().

    :param batch: A GroupResult
    :param wait: If the batch is pending, maximum waiting seconds before the function returns.
    :return: A dict with the overall state and one entry per input in input order.
             The entries of finished inputs are included while the batch is still pending.
    """
    if wait > 0:
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < wait:
            if batch.ready():
                break
            await asyncio.sleep(0.5)

    entries = [_derive_entry(task) for task in batch.results]
    return {
        "state": _derive_batch_state(entries),
        "task_id": batch.id,
        "result": entries
    }


async def getStatus(task_id, wait=0):
    """
    Get the task status.

    The id may identify a batch of tasks (a group) or a single task.

    :param task_id:
    :param wait: If the task is pending, maximum waiting seconds before the function returns.
    :return:
    """

    # A group id queried as a single task would stay pending forever, so check for groups first
    batch = GroupResult.restore(task_id, app=celery)
    if batch is not None:
        return await getBatchStatus(batch, wait)

    task = AsyncResult(task_id, app=celery)

    # Wait
    if wait > 0:
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < wait:
            if task.state != 'PENDING':
                break
            await asyncio.sleep(0.5)

    taskState = _derive_result_state(task.state, task.info)
    response = {
        "state": taskState,
        "task_id": task.id
    }

    if taskState in ('SUCCESS', 'FAILURE', 'MIXED'):
        if isinstance(task.info, Exception):
            response['msg'] = str(task.info)
        else:
            response['result'] = task.info
    return response

class BaseTask(Task):
    # Request = MyRequest
    _wf = None
    _workflowClass = None

    # TODO: Do we need a custom prompt folder?
    promptFolder = os.getenv('PROMPT_FOLDER', '/app/coreresources/prompts')
    customPromptFolder = os.getenv('PROMPT_FOLDER', '/app/coreresources/prompts')
    cacheFolder = os.getenv('DATABOARD_CACHE_FOLDER', 'app/data/.cache')
    logFolder = os.getenv('DATABOARD_LOG_FOLDER', 'app/data/.logs')

    @property
    def wf(self):
        if self._wf is None:
            settings = {
                'promptFolder': self.promptFolder,
                'cacheFolder': self.cacheFolder,
                'logFolder': self.logFolder
            }
            self._wf = self._workflowClass(settings)
        return self._wf

    def prepareSettings(self, payloadOptions):
        workflowSettings = {}

        # Set prompt files
        if self._workflowClass is not None:
            prompts = payloadOptions.get('prompts')
            if prompts is not None and isinstance(prompts, dict):

                workflowSettings['userPrompt'] = prompts.get('user')
                workflowSettings['systemPrompt'] = prompts.get('system')
                workflowSettings['promptFolder'] = False

            elif prompts is not None:
                userPromptFile = self._workflowClass.promptPrefix + '_' + prompts + '_' + 'user' + '.txt'
                self.promptFolder = self.customPromptFolder
                if not os.path.exists(os.path.join(str(self.promptFolder), userPromptFile)):
                    raise ValueError('Unsupported prompt')

                systemPromptFile = self._workflowClass.promptPrefix + '_' + prompts + '_' + 'system' + '.txt'
                if not os.path.exists(os.path.join(str(self.promptFolder), systemPromptFile)):
                    raise ValueError('Unsupported prompt')

                workflowSettings['userPrompt'] = userPromptFile
                workflowSettings['systemPrompt'] = systemPromptFile
                workflowSettings['promptFolder'] = self.promptFolder

        # Disable reporting
        workflowSettings['reportCodings'] = False

        # Answer settings
        workflowSettings['rawAnswer'] = payloadOptions.get('raw', False)

        # Model and server settings
        for key in ['server', 'model', 'temperature']:
            if payloadOptions.get(key, None) is not None:
                workflowSettings[key] = payloadOptions.get(key, None)

        return workflowSettings


class SummarizeTask(BaseTask):
    _workflowClass = SummaryWorkflow

    def prepareSettings(self, payloadOptions):
        workflowSettings = super().prepareSettings(payloadOptions)
        ruleSettings = {
            'mode': payloadOptions.get('mode', 'single'),
            'rules': payloadOptions.get('rules', None)
        }
        return {**workflowSettings, **ruleSettings}

@celery.task(bind=True, base=SummarizeTask)
def summarize(self, data, options={}):
    options = self.prepareSettings(options)
    result = self.wf.dataToData(data, options)
    result = result.drop(['text'], axis=1)
    result = result.replace({np.nan: None, np.inf: None, -np.inf: None})
    result = result.to_dict('records')

    return {'answers':result}


class CodingTask(BaseTask):
    _workflowClass = CodingWorkflow

    def prepareSettings(self, payloadOptions):
        workflowSettings = super().prepareSettings(payloadOptions)
        ruleSettings = {
            'mode': payloadOptions.get('mode', 'single'),
            'rules': payloadOptions.get('rules', None)
        }
        return {**workflowSettings, **ruleSettings}


@celery.task(bind=True, base=CodingTask)
def coding(self, data, options={}):
    workflowSettings = self.prepareSettings(options)
    result = self.wf.dataToData(data, workflowSettings)
    result = result.drop(['text'], axis=1)
    result = result.replace({np.nan: None, np.inf: None, -np.inf: None})
    result = result.to_dict('records')

    return {'answers':result}

class AnnotateTask(BaseTask):
    _workflowClass = AnnoWorkflow

    def prepareSettings(self, payloadOptions):
        workflowSettings = super().prepareSettings(payloadOptions)
        ruleSettings = {
            'rules': payloadOptions.get('rules', None)
        }
        return {**workflowSettings, **ruleSettings}

@celery.task(bind=True, base=AnnotateTask)
def annotate(self, data, options={}):
    workflowSettings = self.prepareSettings(options)
    result = self.wf.dataToData(data, workflowSettings)
    result = result.drop(['text'], axis=1)
    result = result.replace({np.nan: None, np.inf: None, -np.inf: None})
    result = result.to_dict('records')

    return {'answers':result}


class TripleTask(BaseTask):
    _workflowClass = TripleWorkflow

@celery.task(bind=True, base=TripleTask)
def triples(self, data, options={}):
    workflowSettings = self.prepareSettings(options)
    result = self.wf.dataToData(data, workflowSettings)
    triples = self.wf.parseTriples(result.llm_result)

    return {'answers': triples}


class InvalidRequest(ValueError):
    """
    The task request is invalid and the client has to correct it.
    """


class ParseTask(BaseTask):
    _workflowClass = ParseWorkflow

    def prepareSettings(self, payloadOptions):
        return {
            'formalism': payloadOptions.get('formalism'),
            'dialect': payloadOptions.get('dialect'),
            'rules': payloadOptions.get('rules')
        }

@celery.task(bind=True, base=ParseTask)
def parse(self, text, options={}):
    """
    Parse a single text.

    :param text: The text to parse
    :param options: formalism, dialect and rules
    :return: A dict with the keys xml, errors and failed
    """
    workflowSettings = self.prepareSettings(options)
    return self.wf.dataToData([text], workflowSettings)[0]


def submitParse(inputs, options):
    """
    Start one parse task per input, bundled as a group.
    The group is saved so that it can be restored by its id.

    :param inputs: A string or a list of strings
    :param options: formalism, dialect and rules
    :return: The group result. Its id identifies the whole batch.
    :raises InvalidRequest: If an option is missing, or no parser exists for formalism and dialect
    """
    inputs = [inputs] if isinstance(inputs, str) else inputs
    if len(inputs) == 0:
        raise InvalidRequest("No input")

    for name in ('formalism', 'dialect'):
        if not options.get(name):
            raise InvalidRequest(f"Missing option '{name}'")
        if not isinstance(options[name], str):
            raise InvalidRequest(f"Option '{name}' must be a string")

    formalism, dialect = options['formalism'], options['dialect']
    if not has_parser(formalism, dialect):
        raise InvalidRequest(f"No parser for formalism '{formalism}' and dialect '{dialect}'")

    taskOptions = {key: options.get(key) for key in ('formalism', 'dialect', 'rules')}
    batch = group(parse.s(text, taskOptions) for text in inputs).apply_async()
    batch.save()
    return batch
