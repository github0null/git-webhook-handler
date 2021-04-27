#!/usr/bin/env python
import io
import os
import re
import sys
import json
import subprocess
import requests
import ipaddress
import hmac
from hashlib import sha1
from flask import Flask, request, abort

"""
Conditionally import ProxyFix from werkzeug if the USE_PROXYFIX environment
variable is set to true.  If you intend to import this as a module in your own
code, use os.environ to set the environment variable before importing this as a
module.

.. code:: python

    os.environ['USE_PROXYFIX'] = 'true'
    import flask-github-webhook-handler.index as handler

"""
if os.environ.get('USE_PROXYFIX', None) == 'true':
    from werkzeug.contrib.fixers import ProxyFix

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

            # If VALIDATE_SOURCEIP is set to false, do not validate source IP
            if os.environ.get('VALIDATE_SOURCEIP', None) != 'false':

                # If GHE_ADDRESS is specified, use it as the hook_blocks.
                if os.environ.get('GHE_ADDRESS', None):
                    hook_blocks = [str(os.environ.get('GHE_ADDRESS'))]
                # Otherwise get the hook address blocks from the API.
                else:
                    hook_blocks = requests.get('https://api.github.com/meta').json()['hooks']

                # Check if the POST request is from github.com or GHE
                for block in hook_blocks:
                    if ipaddress.ip_address(request_ip) in ipaddress.ip_network(block):
                        break  # the remote_addr is within the network range of github.
                else:
                    if str(request_ip) != '127.0.0.1':
                        return 'error, request ip {0}'.format(request_ip), 403

            if request.headers.get('X-GitHub-Event') == "ping":
                return json.dumps({'msg': 'Hello, I received a ping !'})

            if request.headers.get('X-GitHub-Event') != "push":
                return json.dumps({'msg': "wrong event type"}), 403

            repos = json.loads(io.open(REPOS_JSON_PATH, 'r').read())

            payload = json.loads(request.data)
            repo_meta = {
                'name': payload['repository']['name'],
                'owner': payload['repository']['owner']['name'],
            }

            # repo name
            repo_name = '{owner}/{name}/branch:{branch}'.format(**repo_meta)

            # Try to match on branch as configured in repos.json
            match = re.match(r"refs/heads/(?P<branch>.*)", payload['ref'])
            if match:
                repo_meta['branch'] = match.groupdict()['branch']
                repo = repos.get(repo_name, None)

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
                    if not compare_digest(mac.hexdigest(), signature):
                        return 'error: check sum failed !', 403

            if repo.get('action', None):
                log_txt = []
                for action in repo['action']:
                    subp = subprocess.Popen(action, cwd=repo.get('path', '.'), 
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = subp.communicate()
                    log_txt.append('[{0}]\n{1}\n{2}'.format(repo_name, stdout, stderr))
                return '\n\n'.join(log_txt)

            return 'nothing to do !'

    # goto error
    except Exception as err:

        return 'error: {0}'.format(err), 500
    

# Check if python version is less than 2.7.7
if sys.version_info < (2, 7, 7):
    # http://blog.turret.io/hmac-in-go-python-ruby-php-and-nodejs/
    def compare_digest(a, b):
        """
        ** From Django source **

        Run a constant time comparison against two strings

        Returns true if a and b are equal.

        a and b must both be the same length, or False is
        returned immediately
        """
        if len(a) != len(b):
            return False

        result = 0
        for ch_a, ch_b in zip(a, b):
            result |= ord(ch_a) ^ ord(ch_b)
        return result == 0
else:
    compare_digest = hmac.compare_digest

if __name__ == "__main__":
    
    try:
        port_number = int(sys.argv[1])
    except:
        port_number = 80

    if os.environ.get('USE_PROXYFIX', None) == 'true':
        app.wsgi_app = ProxyFix(app.wsgi_app)

    app.run(host='0.0.0.0', port=port_number)
