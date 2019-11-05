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

GIST_USER = 'grenade'
GIST_SHA = 'a2ff8966607583fbc1944fccc256a80c'


async def create_task(provisioner, workerType, taskGroupId, task, iteration, iterations):
  taskId = slugid.nice()
  payload = {
    'created': '{}Z'.format(datetime.utcnow().isoformat()[:-3]),
    'deadline': '{}Z'.format((datetime.utcnow() + timedelta(days=3)).isoformat()[:-3]),
    'provisionerId': provisioner,
    'workerType': workerType,
    'taskGroupId': taskGroupId,
    'routes': [
      'index.project.releng.a2ff8966607583fbc1944fccc256a80c.{}.{}.{}'.format(provisioner, workerType, task['namespace']),
      'index.project.releng.a2ff8966607583fbc1944fccc256a80c.latest.{}.{}.{}'.format(provisioner, workerType, task['namespace']),
      'index.project.releng.a2ff8966607583fbc1944fccc256a80c.daily.{}.{}.{}.{}'.format(datetime.utcnow().strftime("%Y%m%d"), provisioner, workerType, task['namespace']),
      'index.project.releng.a2ff8966607583fbc1944fccc256a80c.hourly.{}.{}.{}.{}'.format(datetime.utcnow().strftime("%Y%m%d%H"), provisioner, workerType, task['namespace'])
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
      'source': 'https://gist.github.com/{}/{}'.format(GIST_USER, GIST_SHA)
    }
  }
  print('creating {}/{} task {} ({}/{} {}) (https://tools.taskcluster.net/groups/{}/tasks/{})'.format(provisioner, workerType, task['namespace'], iteration, iterations, taskId, os.environ.get('TASK_ID'), taskId))
  return await asyncQueue.createTask(taskId, payload)

  
async def print_task_artifacts(provisioner, workerType, taskGroupId, taskNamespace, task, iteration, iterations):
  global results
  taskStatus = await create_task(provisioner, workerType, taskGroupId, task, iteration, iterations)
  print('{}/{} - {} ({}/{} {}): {}'.format(provisioner, workerType, taskNamespace, iteration, iterations, taskStatus['status']['taskId'], taskStatus['status']['state']))
  while taskStatus['status']['state'] not in ['completed', 'failed']:
    time.sleep(2)
    print('{}/{} - {} ({}/{} {}): {}'.format(provisioner, workerType, taskNamespace, iteration, iterations, taskStatus['status']['taskId'], taskStatus['status']['state']))
    taskStatus = await asyncQueue.status(taskStatus['status']['taskId'])
  print('{}/{} - {} ({}/{} {}): {} on run {}'.format(provisioner, workerType, taskNamespace, iteration, iterations, taskStatus['status']['taskId'], taskStatus['status']['state'], taskStatus['status']['runs'][-1]['runId']))  
  for artifactDefinition in task['artifacts']:
    artifactUrl = 'https://taskcluster-artifacts.net/{}/{}/{}'.format(taskStatus['status']['taskId'], taskStatus['status']['runs'][-1]['runId'], artifactDefinition['name'])
    print('{}/{} - {} ({}/{} {}): {}'.format(provisioner, workerType, taskNamespace, iteration, iterations, taskStatus['status']['taskId'], artifactUrl))
    try:
      artifactContent = decompress(urllib.request.urlopen(urllib.request.Request(artifactUrl)).read()).decode('utf-8')
      if 'file-missing-on-worker' in artifactContent:
        artifactContent = None
    except:
      artifactContent = None
    if artifactContent is not None and 'line' in artifactDefinition:
      if 'split' in artifactDefinition:
        artifactText = artifactContent.strip().split('\n', 1)[artifactDefinition['line']].strip().split(artifactDefinition['split']['separator'])[artifactDefinition['split']['index']].strip(artifactDefinition['split']['strip'] if 'strip' in artifactDefinition['split'] else None)
      elif 'regex' in artifactDefinition:
        artifactText = re.search(artifactDefinition['regex']['match'], artifactContent.split('\n', 1)[artifactDefinition['line']]).group(artifactDefinition['regex']['group'])
      else:
        artifactText = artifactContent.strip().split('\n', 1)[artifactDefinition['line']].strip()
    else:
      artifactText = '' if artifactContent is None else artifactContent.strip()
    print('{}/{} - {} ({}/{} {}): {}: {}'.format(provisioner, workerType, taskNamespace, iteration, iterations, taskStatus['status']['taskId'], artifactDefinition['name'], artifactText))
    run = taskStatus['status']['runs'][-1]['runId']
    if workerType in results:
      if taskNamespace in results[workerType]:
        if iteration in results[workerType][taskNamespace]:
          results[workerType][taskNamespace][iteration].update({ os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText })
        else:
          try:
            results[workerType][taskNamespace].update({ iteration: { 'status': taskStatus['status'], os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText } })
          except Exception as e:
            print('error adding iteration {} to result'.format(iteration), e)
      else:
        try:
          results[workerType].update({ taskNamespace: { iteration: { 'status': taskStatus['status'], os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText } } })
        except Exception as e:
          print('error adding task {} to result'.format(taskNamespace), e)
    else:
      try:
        results.update({ workerType: { taskNamespace: { iteration: { 'status': taskStatus['status'], os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText } } } })
      except Exception as e:
        print('error adding workerType {} to result'.format(workerType), e)
  with open('results.json', 'w') as fp:
    json.dump(results, fp, indent=2, sort_keys=True)


async def close(session):
  await session.close()


config = yaml.load(urllib.request.urlopen('https://gist.githubusercontent.com/{}/{}/raw/debug-config.yml?{}'.format(GIST_USER, GIST_SHA, slugid.nice())).read())
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
print(results)
with open('results.json', 'w') as fp:
  json.dump(results, fp, indent=2, sort_keys=True)
end = time.time()
print("total time: {}".format(end - start))