import asyncio
import os
import json
import slugid
import taskcluster
import time
import urllib
from datetime import datetime, timedelta

GIST_USER = 'grenade'
GIST_SHA = 'a2ff8966607583fbc1944fccc256a80c'


async def create_task(workerType, taskGroupId, task):
  taskId = slugid.nice()
  payload = {
    'created': '{}Z'.format(datetime.utcnow().isoformat()[:-3]),
    'deadline': '{}Z'.format((datetime.utcnow() + timedelta(days=3)).isoformat()[:-3]),
    'provisionerId': 'aws-provisioner-v1',
    'workerType': workerType,
    'taskGroupId': taskGroupId,
    'routes': [],
    'scopes': [],
    'payload': {
      'maxRunTime': task['maxruntime'],
      'command': task['command'],
      'artifacts': task['artifacts'],
      'features': task['features']
    },
    'metadata': {
      'name': '{}{}{}'.format(task['name']['prefix'], workerType, task['name']['suffix']),
      'description': '{}{}{}'.format(task['description']['prefix'], workerType, task['description']['suffix']),
      'owner': task['owner'],
      'source': 'https://gist.github.com/{}/{}'.format(GIST_USER, GIST_SHA)
    }
  }
  print('creating task {} (https://tools.taskcluster.net/groups/{}/tasks/{})'.format(taskId, os.environ.get('TASK_ID'), taskId))
  taskStatusResponse = queue.createTask(taskId, payload)
  print(taskStatusResponse)
  return taskId

  
async def print_task_artifacts(workerType, taskGroupId, task):
  taskId = await create_task(workerType, taskGroupId, task)
  print(taskId)


config = json.loads(urllib.request.urlopen('https://gist.githubusercontent.com/{}/{}/raw/config.json'.format(GIST_USER, GIST_SHA)).read())
# python 2.x
# config = json.loads(urllib.urlopen('https://gist.githubusercontent.com/{}/{}/raw/config.json'.format(GIST_USER, GIST_SHA)).read())
queue = taskcluster.Queue({'rootUrl': os.environ['TASKCLUSTER_PROXY_URL']})

start = time.time()  
loop = asyncio.get_event_loop()

tasks = []
for workerType in config['workertypes']:
  tasks.append(asyncio.ensure_future(print_task_artifacts(workerType, os.environ.get('TASK_ID'), config['task'])))

loop.run_until_complete(asyncio.wait(tasks))  
loop.close()
end = time.time()  
print("Total time: {}".format(end - start))
#https://taskcluster-artifacts.net/cp0c4mkCQiyL-36DPLHwOQ/0/public/windows-version.txt