import asyncio
import os
import json
import re
import slugid
import taskcluster.aio
import time
import urllib
import urllib.request
import yaml
from datetime import datetime, timedelta
from gzip import decompress
from random import randint, seed

seed(1)

GH_ORG = 'mozilla-platform-ops'
GH_REPO = 'worker-observer'


async def create_task(provisioner, workerType, taskGroupId, task, iteration, iterations):
  global asyncQueue
  taskId = slugid.nice()
  payload = {
    'created': '{}Z'.format(datetime.utcnow().isoformat()[:-3]),
    'deadline': '{}Z'.format((datetime.utcnow() + timedelta(days=3)).isoformat()[:-3]),
    'provisionerId': provisioner,
    'workerType': workerType,
    'taskGroupId': taskGroupId,
    'routes': [
      'index.project.relops.mozilla-platform-ops.worker-observer.{}.{}.{}'.format(provisioner, workerType, task['namespace']),
      'index.project.relops.mozilla-platform-ops.worker-observer.latest.{}.{}.{}'.format(provisioner, workerType, task['namespace']),
      'index.project.relops.mozilla-platform-ops.worker-observer.daily.{}.{}.{}.{}'.format(datetime.utcnow().strftime("%Y%m%d"), provisioner, workerType, task['namespace']),
      'index.project.relops.mozilla-platform-ops.worker-observer.hourly.{}.{}.{}.{}'.format(datetime.utcnow().strftime("%Y%m%d%H"), provisioner, workerType, task['namespace'])
    ],
    'scopes': [],
    'payload': {
      'maxRunTime': task['maxruntime'],
      'command': task['command'],
      'artifacts': list(map(lambda x: {'type': x['type'],'name': x['name'],'path': x['path']}, task['artifacts'])),
      'features': task['features']
    },
    'metadata': {
      'name': '{} {}/{} {} :: {}/{}'.format(task['name']['prefix'], provisioner, workerType, task['name']['suffix'], iteration, iterations) if (iterations < 10) else '{}{}/{}{} {:02d}/{}'.format(task['name']['prefix'], provisioner, workerType, task['name']['suffix'], iteration, iterations) if (iterations < 100) else '{}{}/{}{} {:03d}/{}'.format(task['name']['prefix'], provisioner, workerType, task['name']['suffix'], iteration, iterations),
      'description': '{}{}/{}{}'.format(task['description']['prefix'], provisioner, workerType, task['description']['suffix']),
      'owner': task['owner'],
      'source': 'https://github.com/{}/{}'.format(GH_ORG, GH_REPO)
    }
  }
  print('creating {}/{} task {} ({}/{} {}) ({}/groups/{}/tasks/{})'.format(provisioner, workerType, task['namespace'], iteration, iterations, taskId, os.environ.get('TASKCLUSTER_ROOT_URL'), os.environ.get('TASK_ID'), taskId))
  return await asyncQueue.createTask(taskId, payload)

  
async def print_task_artifacts(provisioner, workerType, taskGroupId, taskNamespace, task, iteration, iterations):
  global results, asyncQueue
  taskStatus = await create_task(provisioner, workerType, taskGroupId, task, iteration, iterations)
  print('{}/{} - {} ({}/{} {}): {}'.format(provisioner, workerType, taskNamespace, iteration, iterations, taskStatus['status']['taskId'], taskStatus['status']['state']))
  while taskStatus['status']['state'] not in ['completed', 'failed']:
    await asyncio.sleep(randint(10, 30) if taskStatus['status']['state'] == 'pending' else 0.5)
    print('{}/{} - {} ({}/{} {}): {}'.format(provisioner, workerType, taskNamespace, iteration, iterations, taskStatus['status']['taskId'], taskStatus['status']['state']))
    taskStatus = await asyncQueue.status(taskStatus['status']['taskId'])
  print('{}/{} - {} ({}/{} {}): {} on run {}'.format(provisioner, workerType, taskNamespace, iteration, iterations, taskStatus['status']['taskId'], taskStatus['status']['state'], taskStatus['status']['runs'][-1]['runId']))  
  for artifactDefinition in task['artifacts']:
    artifactUrl = 'https://taskcluster-artifacts.net/{}/{}/{}'.format(taskStatus['status']['taskId'], taskStatus['status']['runs'][-1]['runId'], artifactDefinition['name'])
    print('{}/{} - {} ({}/{} {}): {}'.format(provisioner, workerType, taskNamespace, iteration, iterations, taskStatus['status']['taskId'], artifactUrl))
    try:
      artifactContent = decompress(urllib.request.urlopen(urllib.request.Request(artifactUrl)).read()).decode(artifactDefinition['encoding'] if 'encoding' in artifactDefinition else 'utf-8')
      if 'file-missing-on-worker' in artifactContent:
        artifactContent = None
    except Exception as e:
      print('error fetching artifact {}'.format(artifactUrl), e)
      artifactContent = None
    if artifactContent is not None:
      artifactLine = artifactContent.split('\n')[artifactDefinition['line']].strip() if 'line' in artifactDefinition else artifactContent.strip()
      artifactText = artifactLine.split(artifactDefinition['split']['separator'])[artifactDefinition['split']['index']].strip() if 'split' in artifactDefinition else artifactLine
      if 'regex' in artifactDefinition:
        try:
          artifactText = re.search(artifactDefinition['regex']['match'], artifactText).group(artifactDefinition['regex']['group'])
        except Exception as e:
          artifactText = ''
          print('error matching regex: "{}", group: {}'.format(artifactDefinition['regex']['match'], artifactDefinition['regex']['group']), e)
    else:
      artifactText = ''
    print('{}/{} - {} ({}/{} {}): {}: {}'.format(provisioner, workerType, taskNamespace, iteration, iterations, taskStatus['status']['taskId'], artifactDefinition['name'], artifactText))
    run = taskStatus['status']['runs'][-1]['runId']
    if workerType in results:
      if taskNamespace in results[workerType]:
        if 'iteration-{}'.format(iteration) in results[workerType][taskNamespace]:
          results[workerType][taskNamespace]['iteration-{}'.format(iteration)].update({ 'task': taskStatus['status'], os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText })
        else:
          results[workerType][taskNamespace].update({ 'iteration-{}'.format(iteration): { 'task': taskStatus['status'], os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText } })
      else:
        results[workerType].update({ taskNamespace: { 'iteration-{}'.format(iteration): { 'task': taskStatus['status'], os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText } } })
    else:
      results.update({ workerType: { taskNamespace: { 'iteration-{}'.format(iteration): { 'task': taskStatus['status'], os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText } } } })


async def close(session):
  await session.close()


config = yaml.load(urllib.request.urlopen('https://raw.githubusercontent.com/{}/{}/master/config.yml?{}'.format(GH_ORG, GH_REPO, slugid.nice())).read())
taskclusterOptions = {
  'rootUrl': os.environ['TASKCLUSTER_PROXY_URL']
}

start = time.time()
loop = asyncio.get_event_loop()

session = taskcluster.aio.createSession(loop=loop)
asyncQueue = taskcluster.aio.Queue(taskclusterOptions, session=session)

tasks = []
results = {}
for task in config['tasks']:
  for target in task['targets']:
    for i in range(1, (target['iterations'] + 1)):
      tasks.append(asyncio.ensure_future(print_task_artifacts(target['provisioner'], target['workertype'], os.environ.get('TASK_ID'), task['namespace'], task, i, target['iterations'])))

loop.run_until_complete(asyncio.wait(tasks, timeout=1200))
loop.run_until_complete(close(session))
loop.close()
with open('results.json', 'w') as fp:
  json.dump(results, fp, indent=2, sort_keys=True)
end = time.time()
print("total time: {}".format(end - start))