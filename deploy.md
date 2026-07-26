# 部署与启动

以下命令默认项目部署在 `/root/fund-analysis`，Python 虚拟环境为
`.venv311`，服务端口为 `8765`。这些值与 `update-and-restart.sh`
中的配置一致；如果部署目录或虚拟环境名称不同，需要同步修改脚本顶部的
`PROJECT`、`PYTHON` 和 `PORT`。

## 安装依赖

进入项目目录并激活虚拟环境：

```bash
cd /root/fund-analysis
source .venv311/bin/activate
python -m pip install -r requirements.txt
```

## 直接启动

前台启动，适合调试：

```bash
cd /root/fund-analysis
.venv311/bin/python -m uvicorn app:app \
    --host 0.0.0.0 \
    --port 8765
```

后台启动：

```bash
cd /root/fund-analysis
nohup .venv311/bin/python -m uvicorn app:app \
    --host 0.0.0.0 \
    --port 8765 \
    >> uvicorn.log 2>&1 &
echo $! > uvicorn.pid
```

查看服务状态和日志：

```bash
curl http://127.0.0.1:8765/health
ps -fp "$(cat /root/fund-analysis/uvicorn.pid)"
tail -f /root/fund-analysis/uvicorn.log
```

停止后台服务：

```bash
kill "$(cat /root/fund-analysis/uvicorn.pid)"
```

## 启动并定时更新、重启

`update-and-restart.sh` 会执行以下操作：

1. 如果服务未运行，先执行 `git pull --ff-only`，然后启动服务。
2. 如果服务正在运行，比较 `git pull` 前后的提交。
3. 没有新提交时保持现有进程不变。
4. 有新提交时停止旧进程并启动新进程。
5. 使用文件锁避免多个定时任务同时执行。

首次部署时赋予执行权限并运行一次：

```bash
cd /root/fund-analysis
chmod +x update-and-restart.sh
./update-and-restart.sh
```

确认首次启动成功：

```bash
cat uvicorn.pid
curl http://127.0.0.1:8765/health
tail -n 50 uvicorn.log
```

编辑 root 用户的定时任务：

```bash
crontab -e
```

加入以下内容，每 5 分钟检查一次：

```cron
*/5 * * * * /root/fund-analysis/update-and-restart.sh >> /root/fund-analysis/update-cron.log 2>&1
```

确认定时任务已经保存：

```bash
crontab -l
systemctl is-active crond
```

查看自动更新日志：

```bash
tail -f /root/fund-analysis/update-cron.log
```

手动触发一次更新检查：

```bash
/root/fund-analysis/update-and-restart.sh
```

查看当前部署的提交：

```bash
cd /root/fund-analysis
git rev-parse --short HEAD
```

> CentOS 7 自带的旧版 Git 可能不支持 `git -C`，因此文档统一使用
> `cd /root/fund-analysis` 后再执行 Git 命令。

## Nginx 反向代理

服务通过 Nginx 对外提供时，建议把 Uvicorn 的 `--host` 改为
`127.0.0.1`，并让 Nginx 转发到：

```text
http://127.0.0.1:8765
```

修改监听地址时，需要同时修改直接启动命令和
`update-and-restart.sh` 中的启动参数。
