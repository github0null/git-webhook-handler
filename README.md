## Gitea/Github web hook handler

A web hook handler for gitea/Github

**Need Python3**

***

## install

1. clone this repo and enter repo folder

2. install python requirements: run `pip3 install -r requirements.txt`

3. install as a service: run `vim /usr/lib/systemd/system/gitwebhook.service`

```shell
[Unit]
Description=gitwebhook
Documentation=https://git.github0null.io/root/git-webhook-handler
After=network.target
Wants=network.target

[Service]
User=root
WorkingDirectory=/root
Environment="REPOS_JSON_PATH=/root/githook_repos.json"
ExecStart=/usr/bin/python3 /YOUR_DOWNLOAD_PATH/git-webhook-handler/index.py 18541
Restart=on-abnormal
RestartSec=5s
KillMode=mixed

StandardOutput=syslog
StandardError=syslog

[Install]
WantedBy=multi-user.target
```

create a **/root/githook_repos.json** to descrip hook content, like this:

```json
{
    "razius/puppet": {
        "path": "/home/puppet",
        "key": "MyVerySecretKey",
        "action": [
            "git pull origin master"
        ]
    },
    "d3non/somerandomexample/branch:live": {
        "path": "/home/exampleapp",
        "key": "123456789",
        "action": [
            "git pull origin live",
            "echo execute some commands ..."
        ]
    }
}
```

4. update service: run `systemctl daemon-reload`

5. launch service: run `systemctl start gitwebhook`

5. check your service status: run `systemctl status gitwebhook`

7. add to nginx, run `vim /etc/nginx.conf`, add these contents

```shell
server {
    listen 80;
    server_name githook.domain.io;
    location / {
        proxy_pass http://localhost:18541;
        proxy_set_header Host githook.domain.io;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For  $proxy_add_x_forwarded_for;
    }
}

```

**Now, you can use this url: `http://githook.domain.io` to invoke your hook**

- `http://githook.domain.io` is for **gitea** repos
- `http://githook.domain.io/github` is for **github** repos
