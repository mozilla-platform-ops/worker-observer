import os
import json
import slugid
import taskcluster
import urllib
from datetime import datetime, timedelta

GIST_USER = 'grenade'
GIST_SHA = 'a2ff8966607583fbc1944fccc256a80c'

config = json.loads(urllib.urlopen('https://gist.githubusercontent.com/{}/{}/raw/config.json'.format(GIST_USER, GIST_SHA)).read())
queue = taskcluster.Queue({'rootUrl': config.taskcluster.rooturl})
for workerType in config.workertypes:
  taskId = slugid.nice().decode('utf-8')
  payload = {
    'created': '{}Z'.format(datetime.utcnow().isoformat()[:-3]),
    'deadline': '{}Z'.format((datetime.utcnow() + timedelta(days=3)).isoformat()[:-3]),
    'provisionerId': 'aws-provisioner-v1',
    'workerType': workerType,
    'schedulerId': 'taskcluster-github',
    'taskGroupId': os.environ.get('TASK_ID'),
    'routes': [],
    'scopes': [],
    'payload': {
      'osGroups': [],
      'maxRunTime': 3600,
      'command': [
        'git clone https://gist.github.com/{}.git gist'.format(GIST_SHA),
        'powershell -NoProfile -InputFormat None -File .\\gist\\task.ps1 {}'.format(workerType)
      ],
      'features': {
        'runAsAdministrator': True,
        'taskclusterProxy': True
      }
    },
    'metadata': {
      'name': 'iso-to-ami {}'.format(workerType),
      'description': 'build windows ami from iso for {}'.format(workerType),
      'owner': os.environ.get('GITHUB_HEAD_USER_EMAIL'),
      'source': '{}/commit/{}'.format(os.environ.get('GITHUB_HEAD_REPO_URL'), os.environ.get('GITHUB_HEAD_SHA'))
    }
  }
  print('creating task {} (https://tools.taskcluster.net/groups/{}/tasks/{})'.format(taskId, os.environ.get('TASK_ID'), taskId))
  taskStatusResponse = queue.createTask(taskId, payload)
  print(taskStatusResponse)