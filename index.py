#!/usr/bin/env python3
import io
import os
import re
import sys
import json
import subprocess
import requests
import ipaddress
import hmac
import traceback
from hashlib import sha1, sha256
from flask import Flask, request, abort

# Check if python version is less than 3
if sys.version_info.major < 3:
    raise Exception('Sorry !, We need python3 !')

app = Flask(__name__)
app.debug = os.environ.get('DEBUG') == 'true'

# The repos.json file should be readable by the user running the Flask app,
# and the absolute path should be given by this environment variable.
REPOS_JSON_PATH = os.environ['REPOS_JSON_PATH']

##########################################
#      root route (default: gitea)
##########################################

@app.route("/", methods=['GET', 'POST'])
def index():
    return index_gitea()

##########################################
#           route for gitea
##########################################

@app.route("/gitea", methods=['GET', 'POST'])
def index_gitea():

    x_event_name = 'X-Gitea-Event'
    x_sign_name = 'X-Gitea-Signature'

    try:
        if request.method == 'GET':
            return 'test ok !'

        elif request.method == 'POST':

            req_type = request.headers.get(x_event_name)

            if req_type == "ping":
                return json.dumps({'msg': 'Hello, I received a ping !'})

            if req_type != "push":
                return json.dumps({'msg': "Wrong event type: '{0}'".format(req_type)}), 403

            # parse local repos
            repos = json.loads(io.open(REPOS_JSON_PATH, 'r').read())

            # parse payload
            payload = json.loads(request.data)
            repo_meta = {
                'name': payload['repository']['name'],
                'owner': payload['repository']['owner']['username'],
                'commits': payload['commits'],
            }

            # repo name
            repo_name = 'none'

            # Try to match on branch as configured in repos.json
            match = re.match(r"refs/heads/(?P<branch>.*)", payload['ref'])
            if match:
                try:
                    repo_meta['branch'] = match.groupdict()['branch']
                    repo_name = '{owner}/{name}/branch:{branch}'.format(**repo_meta)
                    repo = repos.get(repo_name, None)
                except Exception as err:
                    pass

            # Fallback to plain owner/name lookup
            if not repo:
                repo_name = '{owner}/{name}'.format(**repo_meta)
                repo = repos.get(repo_name, None)

            if not repo:
                return 'not found target repo ! target_name: {0}, repo_list: {1}'.format(repo_name, repos.keys()), 404
            
            # Check if POST request signature is valid
            key = repo.get('key', None)
            if repo.get('path', None) and key:
                signature = request.headers.get(x_sign_name)
                key = str(key).encode()
                payload_sign = hmac.new(key, msg=request.data, digestmod=sha256).hexdigest()
                if not hmac.compare_digest(payload_sign, signature):
                    return 'error: check "' + x_sign_name + '" failed !, key: "{0}", sign: "{1}"'.format(key, payload_sign), 403

            shell_env = os.environ.copy()

            if type(repo_meta['commits']) == list:
                for commit_inf in repo_meta['commits']:
                    shell_env['COMMIT_MSG'] = '"' + commit_inf['message'].rstrip('\r\n').rstrip('\n') + '"'
                    break

            if repo.get('action', None):
                command_cnt = 0
                log_txt = ['[{0}]\n'.format(repo_name)]
                for action in repo['action']:
                    command_cnt += 1
                    task_name = 'task {0}'.format(command_cnt)
                    if type(action) == str:
                        subp = subprocess.Popen(action, cwd=repo.get('path', '.'),
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf8',
                                                env=shell_env, shell=True)
                        stdout, stderr = subp.communicate()
                    elif type(action.get('command', None)) == str:
                        task_name = action.get('name', task_name)
                        command = action.get('command', "echo 'empty command, nothing to do !'")
                        subp = subprocess.Popen(command, cwd=repo.get('path', '.'),
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf8',
                                                env=shell_env, shell=True)
                        stdout, stderr = subp.communicate()
                    else:
                        stdout = 'ignore this action: "{}" !'.format(action)
                        stderr = 'format error: \'action\' must be a string or a valid object !'
                    if stdout.strip() == '':
                        stdout = 'done !'
                    log_txt.append('--- {0}\n{1}\n{2}\n'.format(task_name, stdout, stderr))
                return '\n'.join(log_txt)

            return 'nothing to do !'

    # goto error
    except Exception as err:

        return 'error: {0}\n{1}'.format(repr(err), traceback.format_exc()), 500


##########################################
#           route for github
##########################################

@app.route("/github", methods=['GET', 'POST'])
def index_github():

    x_event_name = 'X-GitHub-Event'
    x_sign_name = 'X-Hub-Signature-256'

    try:
        if request.method == 'GET':
            return 'test ok !'

        elif request.method == 'POST':

            req_type = request.headers.get(x_event_name)

            if req_type == "ping":
                return json.dumps({'msg': 'Hello, I received a ping !'})

            if req_type != "push":
                return json.dumps({'msg': "Wrong event type: '{0}'".format(req_type)}), 403

            # parse local repos
            repos = json.loads(io.open(REPOS_JSON_PATH, 'r').read())

            # parse payload
            payload = json.loads(request.data)
            repo_meta = {
                'name': payload['repository']['name'],
                'owner': payload['repository']['owner']['name'],
                'commits': payload['commits'],
            }

            # repo name
            repo_name = 'none'

            # Try to match on branch as configured in repos.json
            match = re.match(r"refs/heads/(?P<branch>.*)", payload['ref'])
            if match:
                try:
                    repo_meta['branch'] = match.groupdict()['branch']
                    repo_name = '{owner}/{name}/branch:{branch}'.format(**repo_meta)
                    repo = repos.get(repo_name, None)
                except Exception as err:
                    pass

            # Fallback to plain owner/name lookup
            if not repo:
                repo_name = '{owner}/{name}'.format(**repo_meta)
                repo = repos.get(repo_name, None)

            if not repo:
                return 'not found target repo ! target_name: {0}, repo_list: {1}'.format(repo_name, repos.keys()), 404

            # Check if POST request signature is valid
            key = repo.get('key', None)
            if repo.get('path', None) and key:
                signature = request.headers.get(x_sign_name).replace('sha256=', '', 1)
                key = str(key).encode()
                payload_sign = hmac.new(key, msg=request.data, digestmod=sha256).hexdigest()
                if not hmac.compare_digest(payload_sign, signature):
                    return 'error: check "' + x_sign_name + '" failed !, key: "{0}", sign: "{1}"'.format(key, payload_sign), 403

            shell_env = os.environ.copy()

            if type(repo_meta['commits']) == list:
                for commit_inf in repo_meta['commits']:
                    shell_env['COMMIT_MSG'] = '"' + commit_inf['message'].rstrip('\r\n').rstrip('\n') + '"'
                    break

            if repo.get('action', None):
                command_cnt = 0
                log_txt = ['[{0}]\n'.format(repo_name)]
                for action in repo['action']:
                    command_cnt += 1
                    task_name = 'task {0}'.format(command_cnt)
                    if type(action) == str:
                        subp = subprocess.Popen(action, cwd=repo.get('path', '.'),
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf8',
                                                env=shell_env, shell=True)
                        stdout, stderr = subp.communicate()
                    elif type(action.get('command', None)) == str:
                        task_name = action.get('name', task_name)
                        command = action.get('command', "echo 'empty command, nothing to do !'")
                        subp = subprocess.Popen(command, cwd=repo.get('path', '.'),
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf8',
                                                env=shell_env, shell=True)
                        stdout, stderr = subp.communicate()
                    else:
                        stdout = 'ignore this action: "{}" !'.format(action)
                        stderr = 'format error: \'action\' must be a string or a valid object !'
                    if stdout.strip() == '':
                        stdout = 'done !'
                    log_txt.append('--- {0}\n{1}\n{2}\n'.format(task_name, stdout, stderr))
                return '\n'.join(log_txt)

            return 'nothing to do !'

    # goto error
    except Exception as err:

        return 'error: {0}\n{1}'.format(repr(err), traceback.format_exc()), 500


if __name__ == "__main__":

    try:
        port_number = int(sys.argv[1])
    except:
        port_number = 80

    app.run(host='0.0.0.0', port=port_number)
