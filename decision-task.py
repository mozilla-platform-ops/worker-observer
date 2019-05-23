import os
import json
import slugid
import taskcluster
import urllib
from datetime import datetime, timedelta

GIST_USER = 'grenade'
GIST_SHA = 'a2ff8966607583fbc1944fccc256a80c'

config = json.loads(urllib.urlopen('https://gist.githubusercontent.com/{}/{}/raw/config.json'.format(GIST_USER, GIST_SHA)).read())
queue = taskcluster.Queue({'rootUrl': os.environ['TASKCLUSTER_PROXY_URL']})
for workerType in config['task']['workertypes']:
  taskId = slugid.nice().decode('utf-8')
  payload = {
    'created': '{}Z'.format(datetime.utcnow().isoformat()[:-3]),
    'deadline': '{}Z'.format((datetime.utcnow() + timedelta(days=3)).isoformat()[:-3]),
    'provisionerId': 'aws-provisioner-v1',
    'workerType': workerType,
    'taskGroupId': os.environ.get('TASK_ID'),
    'routes': [],
    'scopes': [],
    'payload': {
      'maxRunTime': config['task']['maxruntime'],
      'command': config['task']['command'],
      'features': config['task']['features']
    },
    'metadata': {
      'name': '{}{}{}'.format(config['task']['name']['prefix'], workerType, config['task']['name']['suffix']),
      'description': '{}{}{}'.format(config['task']['description']['prefix'], workerType, config['task']['description']['suffix']),
      'owner': config['task']['owner'],
      'source': 'https://gist.github.com/{}/{}'.format(GIST_USER, GIST_SHA)
    }
  }
  print('creating task {} (https://tools.taskcluster.net/groups/{}/tasks/{})'.format(taskId, os.environ.get('TASK_ID'), taskId))
  taskStatusResponse = queue.createTask(taskId, payload)
  print(taskStatusResponse)