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
from hashlib import sha1
from flask import Flask, request, abort

# Check if python version is less than 3
if sys.version_info.major < 3:
    raise Exception('Sorry !, We need python3 !')

app = Flask(__name__)
app.debug = os.environ.get('DEBUG') == 'true'

# The repos.json file should be readable by the user running the Flask app,
# and the absolute path should be given by this environment variable.
REPOS_JSON_PATH = os.environ['REPOS_JSON_PATH']

@app.route("/", methods=['GET', 'POST'])
def index():

    try:
        if request.method == 'GET':
            return 'test ok !'

        elif request.method == 'POST':
            # Store the IP address of the requester
            request_ip = ipaddress.ip_address(u'{0}'.format(request.remote_addr))

            if request.headers.get('X-GitHub-Event') == "ping":
                return json.dumps({'msg': 'Hello, I received a ping !'})

            if request.headers.get('X-GitHub-Event') != "push":
                return json.dumps({'msg': "wrong event type"}), 403

            repos = json.loads(io.open(REPOS_JSON_PATH, 'r').read())

            payload = json.loads(request.data)
            repo_meta = {
                'name': payload['repository']['name'],
                'owner': payload['repository']['owner']['username'],
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
                return 'not found target repo ! [repo name]: {0}'.format(repo_name), 404

            if repo.get('path', None):
                # Check if POST request signature is valid
                key = repo.get('key', None)
                if key:
                    signature = request.headers.get('X-Hub-Signature').split('=')[1]
                    if type(key) == str:
                        key = key.encode()
                    mac = hmac.new(key, msg=request.data, digestmod=sha1)
                    if not hmac.compare_digest(mac.hexdigest(), signature):
                        return 'error: check signature failed !', 403

            if repo.get('action', None):
                log_txt = []
                for action in repo['action']:
                    subp = subprocess.Popen(action, cwd=repo.get('path', '.'),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf8')
                    stdout, stderr = subp.communicate()
                    log_txt.append('[{0}]\n{1}\n{2}'.format(repo_name, stdout, stderr))
                return '\n\n'.join(log_txt)

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
