# 狼人杀 · AI 推理游戏

FastAPI + WebSocket 多人狼人杀游戏服务器，AI 玩家由 DeepSeek 驱动。

## 特性

- **6 人 / 12 人局**可切换
- **AI 玩家性格系统**：每种角色有独立的行为策略
- **实时 WebSocket 推送**：思考过程、发言、投票全程可见
- **法官串词 + 点名系统**：完整游戏流程模拟
- **暂停 / 恢复**：中途可暂停，前端断开自动暂停
- **防破产机制**：token 消耗控制，HTTP 请求可真正 cancel

## 快速开始

```bash
# 安装依赖
pip install fastapi uvicorn websockets httpx

# 启动服务器
uvicorn werewolf_server:app --host 0.0.0.0 --port 8081

# 打开前端
http://127.0.0.1:8081
```

或双击 `启动狼人杀.bat` 一键启动。

## 文件结构

| 文件 | 说明 |
|------|------|
| `werewolf_server.py` | FastAPI 主服务器，WebSocket + REST API |
| `game_engine.py` | 游戏引擎核心，角色分配、阶段推进、AI 决策 |
| `patch_engine.py` | 热修复补丁模块 |
| `add_judge.py` | 法官串词脚本 |
| `add_rollcall.py` | 点名系统脚本 |
| `socks_relay.py` | SOCKS5 TCP 中继（穿透代理用） |

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 游戏前端页面 |
| `/ws` | WebSocket | 实时游戏数据推送 |
| `/api/start` | POST | 开始新游戏 |
| `/api/stop` | POST | 暂停游戏 |
| `/api/resume` | POST | 恢复游戏 |
| `/api/config` | POST | 配置游戏（人数等） |

## 游戏流程

```
玩家就绪 → 发身份 → 夜晚（狼人刀人/预言家查验/女巫用药）
→ 白天（公布死讯 → 发言 → 投票放逐）→ 循环 → 胜负判定
```
