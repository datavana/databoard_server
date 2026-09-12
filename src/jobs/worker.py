import os

import numpy as np
#from kombu import Connection, Queue
import asyncio

from celery import Celery, Task
from celery.result import AsyncResult
from celery.app import trace

from databoard_core.flows import CodingWorkflow
from databoard_core.flows import SummaryWorkflow
from databoard_core.flows import AnnoWorkflow
from databoard_core.flows import TripleWorkflow

# Remove data from log
trace.LOG_SUCCESS = """\
Task %(name)s[%(id)s] succeeded in %(runtime)ss\
"""

# Start Celery
os.makedirs('/app/data/.jobs', exist_ok=True)
brokerHost = os.getenv('RABBITMQ_HOST', 'rabbitmq')
brokerUrl = 'amqp://guest:guest@' + brokerHost
celery = Celery(
    'tasks',
    broker=brokerUrl,
    backend='file:///app/data/.jobs'
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


async def getStatus(task_id, wait=0):
    """
    Get the task status.

    :param task_id:
    :param wait: If the task is pending, maximum waiting seconds before the function returns.
    :return:
    """

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
