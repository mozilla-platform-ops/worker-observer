import asyncio
import os
import json
import re
import slugid
import taskcluster
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
    'routes': [],
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
  print('creating {}/{} task {} (https://tools.taskcluster.net/groups/{}/tasks/{})'.format(provisioner, workerType, taskId, os.environ.get('TASK_ID'), taskId))
  return queue.createTask(taskId, payload)

  
async def print_task_artifacts(provisioner, workerType, taskGroupId, task, iteration, iterations):
  taskStatus = await create_task(provisioner, workerType, taskGroupId, task, iteration, iterations)
  print('{}/{} - {}: {}'.format(provisioner, workerType, taskStatus['status']['taskId'], taskStatus['status']['state']))
  while taskStatus['status']['state'] not in ['completed', 'failed']:
    time.sleep(2)
    print('{}/{} - {}: {}'.format(provisioner, workerType, taskStatus['status']['taskId'], taskStatus['status']['state']))
    taskStatus = await asyncQueue.status(taskStatus['status']['taskId'])
  print('{}/{} - {}: {} on run {}'.format(provisioner, workerType, taskStatus['status']['taskId'], taskStatus['status']['state'], taskStatus['status']['runs'][-1]['runId']))  
  for artifactDefinition in task['artifacts']:
    artifactUrl = 'https://taskcluster-artifacts.net/{}/{}/{}'.format(taskStatus['status']['taskId'], taskStatus['status']['runs'][-1]['runId'], artifactDefinition['name'])
    print('{}/{} - {}'.format(provisioner, workerType, artifactUrl))
    if 'line' in artifactDefinition:
      if 'split' in artifactDefinition:
        artifactText = decompress(urllib.request.urlopen(urllib.request.Request(artifactUrl)).read()).decode('utf-8').strip().split('\n', 1)[artifactDefinition['line']].strip().split(artifactDefinition['split']['separator'])[artifactDefinition['split']['index']].strip(artifactDefinition['split']['strip'] if 'strip' in artifactDefinition['split'] else None)
      elif 'regex' in artifactDefinition:
        artifactText = re.search(artifactDefinition['regex']['match'], decompress(urllib.request.urlopen(urllib.request.Request(artifactUrl)).read()).decode('utf-8').split('\n', 1)[artifactDefinition['line']]).group(artifactDefinition['regex']['group'])
      else:
        artifactText = decompress(urllib.request.urlopen(urllib.request.Request(artifactUrl)).read()).decode('utf-8').strip().split('\n', 1)[artifactDefinition['line']].strip()
    else:
      artifactText = decompress(urllib.request.urlopen(urllib.request.Request(artifactUrl)).read()).decode('utf-8').strip()
    print('{}/{} - {}: {}'.format(provisioner, workerType, artifactDefinition['name'], artifactText))
    taskResultName = task['name']['suffix'].strip(' :')
    run = taskStatus['status']['runs'][-1]['runId']
    if workerType in results:
      if taskResultName in results[workerType]:
        if iteration in results[workerType][taskResultName]:
          results[workerType][taskResultName][iteration].update({ os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText })
        else:
          results[workerType][taskResultName].update({ iteration: { 'status': taskStatus['status'], os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText } })
      else:
        results[workerType].update({ taskResultName: { iteration: { 'status': taskStatus['status'], os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText } } })
    else:
      results.update({ workerType: { taskResultName: { iteration: { 'status': taskStatus['status'], os.path.splitext(os.path.basename(artifactDefinition['name']))[run]: artifactText } } } })


config = yaml.load(urllib.request.urlopen('https://gist.githubusercontent.com/{}/{}/raw/config.yml?{}'.format(GIST_USER, GIST_SHA, slugid.nice())).read())
taskclusterOptions = {
  'rootUrl': os.environ['TASKCLUSTER_PROXY_URL']
}
queue = taskcluster.Queue(taskclusterOptions)

start = time.time()
loop = asyncio.get_event_loop()

session = taskcluster.aio.createSession(loop=loop)
asyncQueue = taskcluster.aio.Queue(taskclusterOptions, session=session)

tasks = []
results = {}
for task in config['tasks']:
  for target in task['targets']:
    for i in range(1, (target['iterations'] + 1)):
      tasks.append(asyncio.ensure_future(print_task_artifacts(target['provisioner'], target['workertype'], os.environ.get('TASK_ID'), task, i, target['iterations'])))

loop.run_until_complete(asyncio.wait(tasks, timeout=1200))
loop.close()
print(results)
with open('results.json', 'w') as fp:
    json.dump(results, fp, indent=2, sort_keys=True)
end = time.time()
print("total time: {}".format(end - start))
