#!/bin/bash
set -u

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

PROJECT="/root/fund-analysis"
PYTHON="$PROJECT/.venv311/bin/python"
PID_FILE="$PROJECT/uvicorn.pid"
APP_LOG="$PROJECT/uvicorn.log"
PORT="8765"

# 防止上一次检查还没结束，下一次又启动
exec 9>/tmp/fund-analysis-update.lock
flock -n 9 || exit 0

log() {
    echo "$(date '+%F %T') $*"
}

is_our_process() {
    local pid="$1"
    local cwd
    local cmd

    [[ -d "/proc/$pid" ]] || return 1

    cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
    cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"

    [[ "$cwd" == "$PROJECT" ]] &&
    [[ "$cmd" == *"uvicorn app:app"* ]] &&
    [[ "$cmd" == *"--port $PORT"* ]]
}

find_running_pid() {
    local pid

    if [[ -f "$PID_FILE" ]]; then
        pid="$(cat "$PID_FILE")"
        if is_our_process "$pid"; then
            echo "$pid"
            return
        fi
    fi

    while read -r pid; do
        if is_our_process "$pid"; then
            echo "$pid"
            return
        fi
    done < <(pgrep -f "uvicorn app:app" 2>/dev/null || true)
}

start_service() {
    cd "$PROJECT" || return 1

    nohup "$PYTHON" -m uvicorn app:app \
        --host 0.0.0.0 \
        --port "$PORT" \
        9>&- \
        >> "$APP_LOG" 2>&1 &

    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"

    sleep 2

    if is_our_process "$new_pid"; then
        log "服务启动成功，PID=$new_pid"
    else
        log "服务启动失败，请查看 $APP_LOG"
        return 1
    fi
}

stop_service() {
    local pid="$1"

    log "停止旧服务，PID=$pid"
    kill "$pid"

    for ignored in {1..15}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$PID_FILE"
            return
        fi
        sleep 1
    done

    log "服务未正常退出，强制停止"
    kill -9 "$pid"
    rm -f "$PID_FILE"
}

cd "$PROJECT" || exit 1

running_pid="$(find_running_pid)"

# 没有运行就拉取一次代码并直接启动
if [[ -z "$running_pid" ]]; then
    log "未检测到运行中的服务"

    if ! git pull --ff-only; then
        log "git pull 失败，使用当前代码启动"
    fi

    start_service
    exit $?
fi

# 服务正在运行：比较 pull 前后的 commit
before_commit="$(git rev-parse HEAD)"

if ! git pull --ff-only; then
    log "git pull 失败，保留当前运行中的服务"
    exit 1
fi

after_commit="$(git rev-parse HEAD)"

if [[ "$before_commit" == "$after_commit" ]]; then
    log "代码没有更新，服务保持运行，PID=$running_pid"
    exit 0
fi

log "检测到更新：$before_commit -> $after_commit"
stop_service "$running_pid"
start_service