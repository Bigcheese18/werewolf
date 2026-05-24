"""
狼人杀 12人局 WebSocket 服务器
FastAPI + WebSocket, with stop/resume support
"""
import asyncio, json, os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from game_engine import init_game, run_game, GameState, Phase

app = FastAPI()

# ── 静态文件 ──
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
INDEX_HTML = os.path.join(TEMPLATES_DIR, "index.html")

# ── 全局状态 ──
game = GameState()
ws_connections = set()
game_task = None


async def broadcast():
    """广播当前游戏状态到所有WebSocket"""
    global game

    # 防破产机制：没有前端连接且游戏未结束时自动挂起，停止消耗 Token
    if len(ws_connections) == 0 and game and not game.stopped and game.phase and game.phase != Phase.GAME_OVER:
        game.stopped = True
        game.add_log("⏸️ 前端已断开，游戏自动暂停", "system", "sys-phase")
        print("⚠️ 所有前端网页已关闭，游戏自动挂起防止后台无限消耗 API Tokens")
        return

    dead = set()
    d = game.to_dict()
    # 截断日志和行动记录，只发最近20条，防止包体过大
    d['game_log'] = d['game_log'][-20:]
    d['action_feed'] = d['action_feed'][-20:]
    data = json.dumps(d, ensure_ascii=False)
    for ws in list(ws_connections):
        try:
            await ws.send_text(data)
        except:
            dead.add(ws)
    ws_connections.difference_update(dead)


@app.get("/")
async def index():
    return FileResponse(INDEX_HTML, media_type="text/html")


@app.get("/state")
async def get_state():
    return JSONResponse(game.to_dict())


@app.post("/start")
async def start_game():
    global game, game_task
    if game.stopped:
        # 暂停时协程正常会停在 maybe_pause；若旧逻辑曾让协程退出，则补一个任务兜底。
        game.stopped = False
        game.add_log("▶️ 游戏继续...", "system", "sys-phase")
        if not game_task or game_task.done():
            game_task = asyncio.create_task(run_game(game, broadcast))
            game.add_log("🔁 暂停任务已恢复运行", "system", "sys-phase")
        await broadcast()
        return JSONResponse({"status": "resumed"})
    if game.phase and game.phase != Phase.GAME_OVER:
        return JSONResponse({"error": "游戏已在进行中"})
    if game_task and not game_task.done():
        game_task.cancel()
    # 保存旧设置，防止被清空
    saved_model = game.ai_model
    saved_configs = game.player_configs
    saved_count = game.player_count
    game = init_game(saved_count)
    game.ai_model = saved_model
    game.player_configs = saved_configs
    game.player_count = saved_count
    game_task = asyncio.create_task(run_game(game, broadcast))
    return JSONResponse({"status": "started"})


@app.post("/stop")
async def stop_game():
    global game, game_task
    if game:
        game.stopped = True
        game.add_log("⏸️ 游戏已手动停止", "system", "sys-phase")
    await broadcast()
    return JSONResponse({"status": "stopped"})


@app.post("/reset")
async def reset_game():
    global game, game_task
    # 先停旧游戏
    if game_task and not game_task.done():
        game_task.cancel()
        try:
            await asyncio.wait_for(game_task, timeout=5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    # 保存旧设置，防止重置后丢失
    saved_model = game.ai_model
    saved_configs = game.player_configs
    saved_count = game.player_count
    game = GameState()
    # 恢复旧设置
    game.ai_model = saved_model
    game.player_configs = saved_configs
    game.player_count = saved_count
    game_task = None
    await broadcast()
    return JSONResponse({"status": "reset"})


class SettingsConfig(BaseModel):
    ai_model: str
    player_configs: dict = {}  # 玩家专属 API 配置 {name: {model, api_key, api_base}}
    player_count: int = 12  # 6人局 / 12人局

@app.post("/settings")
async def update_settings(config: SettingsConfig):
    global game, game_task
    count_changed = (game.player_count != config.player_count)
    game.ai_model = config.ai_model
    game.player_configs = config.player_configs
    game.player_count = config.player_count
    # 人数变了且游戏未开始，原地重新洗牌
    if count_changed and (not game.phase or game.phase == Phase.GAME_OVER or game.round == 0):
        if game_task and not game_task.done():
            game_task.cancel()
        saved_model = game.ai_model
        saved_configs = game.player_configs
        saved_count = game.player_count
        game = init_game(saved_count)
        game.ai_model = saved_model
        game.player_configs = saved_configs
        game.player_count = saved_count
    await broadcast()
    return JSONResponse({"status": "success", "ai_model": game.ai_model, "player_count": game.player_count})


# ── WebSocket ──
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_connections.add(ws)
    d = game.to_dict()
    await ws.send_text(json.dumps(d, ensure_ascii=False))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_connections.discard(ws)
        if len(ws_connections) == 0 and game and not game.stopped:
            game.stopped = True
            game.add_log("⏸️ 前端已断开，游戏自动暂停", "system", "sys-phase")
    except Exception:
        ws_connections.discard(ws)
        if len(ws_connections) == 0 and game and not game.stopped:
            game.stopped = True

