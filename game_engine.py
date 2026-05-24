"""
狼人杀 12人标准局 游戏引擎
4狼4民4神：预言家、女巫、猎人、守卫 (屠边局)
"""
import re, json, random, os, asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import httpx

# Load DeepSeek API key from Hermes auth.json
_auth_path = os.path.expanduser("~/AppData/Local/hermes/auth.json")
if os.path.exists(_auth_path):
    try:
        with open(_auth_path) as f:
            _auth = json.load(f)
        _creds = _auth.get("credential_pool", {}).get("deepseek", [])
        if _creds:
            DEEPSEEK_API_KEY = _creds[0]["access_token"]
        else:
            DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    except:
        DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
else:
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# ── 玩家配置 ──
PLAYER_NAMES = [f"{i}号" for i in range(1, 13)]

ROLE_POOL = [
    "狼人", "狼人", "狼人", "狼人",
    "平民", "平民", "平民", "平民",
    "预言家", "女巫", "猎人", "守卫",
]

ROLE_TEAM = {
    "狼人": "狼人阵营",
    "平民": "好人阵营",
    "预言家": "好人阵营",
    "女巫": "好人阵营",
    "猎人": "好人阵营",
    "守卫": "好人阵营",
}

# ── 阶段枚举 ──
class Phase(Enum):
    NIGHT_GUARD = "守卫行动"
    NIGHT_WOLF = "狼人行动"
    NIGHT_WITCH = "女巫行动"
    NIGHT_SEER = "预言家行动"
    DAY_DISCUSSION = "白天讨论"
    DAY_VOTE = "投票"
    DAY_VOTE_RESULT = "投票结果"
    GAME_OVER = "游戏结束"

# ── AI 调用 ──
import asyncio

async def call_ai(system_prompt, user_message, model=None, game=None):
    """异步调用 API，支持按玩家动态切换模型和接口"""
    if game:
        while game.stopped:
            await asyncio.sleep(0.1)

    # 默认使用全局配置
    actual_model = game.ai_model if game else (model or "deepseek-chat")
    actual_key = DEEPSEEK_API_KEY
    actual_base = DEEPSEEK_API_URL

    # 从 Prompt 中嗅探当前是哪个玩家，匹配独立 API 配置
    player_name = None
    m = re.search(r"你的名字是：(\d+号)", system_prompt)
    if m:
        player_name = m.group(1)
    if game and player_name and player_name in game.player_configs:
        cfg = game.player_configs[player_name]
        actual_model = cfg.get("model") or actual_model
        actual_key = cfg.get("api_key") or actual_key
        actual_base = cfg.get("api_base") or actual_base

    _token = game.game_token if game else None
    seed = random.randint(10000, 99999)
    payload = {
        "model": actual_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.9,
        "seed": seed,
    }
    headers = {
        "Authorization": f"Bearer {actual_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(actual_base, json=payload, headers=headers)
        # 废弃过期请求：游戏已重置但请求还在路上
        if _token is not None and (game is None or game.game_token != _token):
            return "", ""
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content", "")

        # Split 💭 thinking and 🎬 speech
        thinking, speech = "", content
        if "💭" in content:
            parts = re.split(r"[🎬🗣️🗣]", content, maxsplit=1)
            if len(parts) >= 2:
                thinking = parts[0].replace("💭", "").strip()
                speech = parts[1].strip()
            else:
                thinking = ""
                speech = content
        elif "【思考" in content:
            parts = re.split(r"[【【]?(思考|发言|行动)[】:]?", content, maxsplit=1)
            if len(parts) >= 2:
                thinking = parts[0].strip()
                speech = parts[1].strip()
            else:
                speech = content

        # Tag stripping for speech
        for prefix in ["公开发言/行动：", "公开发言：", "发言：", "行动："]:
            if speech.startswith(prefix):
                speech = speech[len(prefix):].strip()
        if speech.startswith("（") and speech.endswith("）"):
            speech = speech[1:-1].strip()

        return thinking, speech
    except asyncio.CancelledError:
        raise  # 让 task.cancel() 真正生效
    except Exception as e:
        return f"[API Error: {e}]", f"[API Error: {e}]"


def parse_action_json(content):
    """从AI输出中提取JSON行动目标"""
    try:
        m = re.search(r"\{[^}]*\}", content)
        if m:
            data = json.loads(m.group())
            if "target" in data:
                return int(data["target"])
            if "vote" in data:
                return int(data["vote"])
            if "save" in data or "poison" in data:
                return data  # Return dict for witch
    except:
        pass
    return None


def parse_witch_json(content):
    """解析女巫的救/毒JSON"""
    save_t, poison_t = None, None
    try:
        m = re.search(r"\{[^}]*\}", content)
        if m:
            d = json.loads(m.group())
            if "save" in d: save_t = int(d["save"])
            if "poison" in d: poison_t = int(d["poison"])
    except:
        pass
    return save_t, poison_t


def clean_public_speech(speech):
    """去掉行动JSON，只保留适合展示和进入公共记忆的发言。"""
    speech = re.sub(r"\s*\{[^}]*\}\s*", " ", speech or "").strip()
    speech = re.sub(r"^[\s🎬💬🗣️🎤📢]+", "", speech).strip()
    speech = re.sub(r"[【\[]\s*(?:公开发言|发言|行动|投票)\s*[】\]]\s*[:：]?", "", speech)
    speech = re.sub(r"(?:^|[，。；;！？\s])[\s🎬💬🗣️🎤]*\d+号\s*(?:公开发言|发言|投票|行动)\s*[:：]\s*", " ", speech)
    speech = re.sub(r"(?:^|[，。；;！？\s])[\s🎬💬🗣️🎤]*(?:我的)?(?:公开)?(?:发言|投票|行动)\s*[:：]\s*", " ", speech)
    return re.sub(r"\s{2,}", " ", speech).strip()


def sanitize_for_player_count(text, player_count):
    """按局型清洗不可能存在的角色信息，避免AI把通用规则带进来。"""
    text = text or ""
    if player_count == 6:
        text = re.sub(r"同守同救", "女巫用药或狼人空刀", text)
        text = re.sub(r"(?:或|和|、)?守卫(?:守中|守护|救人|救了|保人|保护)?", "", text)
        text = re.sub(r"守中", "女巫用药或狼人空刀", text)
        text = re.sub(r"守护", "保护", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def get_action_parse_text(action):
    """读取内部原始行动文本，避免展示层清洗导致JSON丢失。"""
    return f"{action.get('raw_speech', action.get('speech', ''))}\n{action.get('thinking', '')}"


# ── 游戏状态 ──
@dataclass
class Player:
    idx: int           # 1-12
    name: str          # "1号"
    role: str
    team: str
    alive: bool = True
    role_revealed: bool = False
    last_guarded: Optional[int] = None  # 守卫上次守的座位号

@dataclass
class GameState:
    players: list = field(default_factory=list)
    phase: Optional[Phase] = None
    round: int = 0
    seq: int = 0
    game_log: list = field(default_factory=list)    # [{seq, type, content, cls}]
    action_feed: list = field(default_factory=list) # [{seq, player, type, thinking, speech}]
    player_actions: dict = field(default_factory=dict)

    ai_model: str = "deepseek-chat"  # 可热切换，默认 V3
    player_configs: dict = field(default_factory=dict)
    player_count: int = 12

    # Night state
    guard_target: Optional[int] = None
    wolf_target: Optional[int] = None
    witch_save: Optional[int] = None
    witch_poison: Optional[int] = None
    seer_target: Optional[int] = None
    seer_result: Optional[str] = None
    hunter_target: Optional[int] = None
    hunter_shot: bool = False

    witch_used_save: bool = False
    witch_used_poison: bool = False
    first_night: bool = True  # 首夜女巫可自救
    stopped: bool = False
    ceremony_done: bool = False
    game_token: int = 0  # 每次新游戏随机生成，用于废弃过期请求

    def add_log(self, content, type="game", cls=""):
        self.seq += 1
        self.game_log.append({"seq": self.seq, "type": type, "content": content, "cls": cls})

    def add_action(self, player_name, action_type, thinking, speech, extra=None):
        public_thinking = sanitize_for_player_count(thinking, self.player_count)
        public_speech = clean_public_speech(sanitize_for_player_count(speech, self.player_count))
        if player_name not in self.player_actions:
            self.player_actions[player_name] = {}
        action_data = {
            "thinking": public_thinking,
            "speech": public_speech,
            "raw_speech": speech,
        }
        if extra:
            action_data.update(extra)
        self.player_actions[player_name][action_type] = action_data
        self.seq += 1
        feed_item = {
            "seq": self.seq, "player": player_name, "type": action_type,
            "thinking": public_thinking, "speech": public_speech,
        }
        if extra:
            feed_item.update(extra)
        self.action_feed.append(feed_item)

    def get_alive_players(self):
        return [p for p in self.players if p.alive]

    def get_players_by_role(self, role):
        return [p for p in self.players if p.role == role and p.alive]

    def to_dict(self):
        players_data = []
        for p in self.players:
            p_model = self.ai_model
            if p.name in self.player_configs and self.player_configs[p.name].get("model"):
                p_model = self.player_configs[p.name]["model"]
            players_data.append({
                "name": p.name,
                "role": p.role if p.role_revealed else None,
                "alive": p.alive,
                "team": p.team,
                "model": p_model,
            })
        return {
            "players": players_data,
            "phase": self.phase.value if self.phase else None,
            "round": self.round,
            "game_log": self.game_log,
            "action_feed": self.action_feed,
            "ai_model": self.ai_model,
            "player_configs": self.player_configs,
            "player_count": self.player_count,
        }


def init_game(player_count=12):
    g = GameState()
    g.player_count = player_count
    if player_count == 6:
        pool = ["狼人", "狼人", "平民", "平民", "预言家", "女巫"]
    else:
        pool = ["狼人", "狼人", "狼人", "狼人", "平民", "平民", "平民", "平民", "预言家", "女巫", "猎人", "守卫"]
    random.shuffle(pool)
    for i in range(player_count):
        role = pool[i]
        g.players.append(Player(
            idx=i+1, name=f"{i+1}号",
            role=role, team=ROLE_TEAM[role],
        ))
    g.add_log(f"🎮 {player_count}人局狼人杀即将开始！", "system", "sys-phase")
    g.game_token = random.randint(100000, 999999)
    return g


def build_rules_text(g):
    """按局数生成规则提示，避免6人局混入守卫/猎人信息。"""
    if g.player_count == 6:
        return """· 本局6人娱乐局角色：2狼、2民、预言家、女巫；没有其他神职。
· 本局明确没有守卫。公开发言和内心推理都禁止提到守卫、守护、守中、同守同救。
· 夜晚顺序：狼人行动 → 女巫行动 → 预言家行动；预言家获得查验结果后才闭眼。
· 女巫只知道当晚狼刀目标；平安夜只可能来自女巫解药、狼人空刀或实际结算，不得归因于守卫。
· 狼人夜间意见只在存活狼人之间共享；死亡玩家不能继续讨论、投票或夜间行动。
· 预言家查验结果、女巫用药只进入本人私密记忆，除非法官公开宣布或本人白天发言透露。"""
    return """· 夜晚顺序：守卫行动 → 狼人行动 → 女巫行动 → 预言家行动；预言家获得查验结果后才闭眼。
· 女巫只知道当晚狼刀目标，不知道守卫守护目标；守卫不知道狼刀目标和女巫用药。
· 同一名被狼刀玩家若同时被守卫守护并被女巫解药救起，按“同守同救”处理：该玩家仍死亡。
· 狼人夜间意见只在存活狼人之间共享；死亡玩家不能继续讨论、投票或夜间行动。
· 预言家查验结果、女巫用药、守卫目标只进入本人私密记忆，除非法官公开宣布或本人白天发言透露。"""


def build_identity_prompt(g, player):
    """构建AI玩家的身份prompt（只含身份+约束，不含格式）"""
    role_desc = {
        "狼人": f"你的身份是狼人。你和你的狼队友每晚可以共同选择击杀一名玩家。白天你要伪装成好人，保护狼队友。你的生存目标是杀死所有平民或者所有神职。",
        "平民": f"你的身份是平民。你没有特殊能力，但你有思考和投票权。你的目标是白天通过发言和投票找出所有狼人并放逐他们。",
        "预言家": f"你的身份是预言家。每晚你可以查验一名玩家的真实身份（好人或狼人）。你要用信息引导好人阵营走向胜利。",
        "女巫": f"你的身份是女巫。你有一瓶解药和一瓶毒药。解药可以救活被狼人杀害的玩家，毒药可以毒杀任意一名玩家。同一晚不能同时使用两瓶药。首夜可自救。",
        "猎人": f"你的身份是猎人。当你被狼人杀害或被投票出局时，你可以开枪带走一名玩家。如果你被女巫毒死，则不能开枪。",
        "守卫": f"你的身份是守卫。每晚可以守护一名玩家，被守护的玩家当晚不会被狼人杀害。不能连续两晚守护同一人。",
    }

    win_cond = "你和你的存活狼队友需要消灭所有平民或者所有神职即可胜利。" if player.team == "狼人阵营" else "你的目标是找出并放逐所有狼人。"
    role_info = role_desc.get(player.role, f"你的身份是{player.role}。")
    alive_names = [p.name for p in g.get_alive_players()]
    dead_names = [p.name for p in g.players if not p.alive]
    status_lines = [
        f"当前存活玩家：{', '.join(alive_names) if alive_names else '无'}",
        f"已出局玩家：{', '.join(dead_names) if dead_names else '无'}",
    ]
    if player.team == "狼人阵营":
        alive_mates = [p.name for p in g.players if p.team == "狼人阵营" and p.alive and p.name != player.name]
        dead_mates = [p.name for p in g.players if p.team == "狼人阵营" and not p.alive and p.name != player.name]
        status_lines.append(f"当前可与你配合的存活狼队友：{', '.join(alive_mates) if alive_mates else '无'}")
        status_lines.append(f"已出局狼队友：{', '.join(dead_mates) if dead_mates else '无'}；不要向已出局队友提问、协商或安排刀人。")

    return f"""你正在参与一场{g.player_count}人狼人杀游戏，你是一名沉浸式参与的玩家。

【你的身份信息】
你的名字是：{player.name}
你的真实身份是：{player.role}
你的阵营是：{player.team}
{role_info}
{win_cond}

【当前场上状态】
{chr(10).join(status_lines)}

【严禁触发的违规行为（防幻觉规则）】
· 禁止时间穿越：如果当前是第一天，说明游戏刚刚开始，你没有经历过任何之前的夜晚或白天讨论。
· 禁止上帝视角：你不知道其他玩家的真实身份（除非你是狼人且队友已经透露过、或你是预言家查验过）。
· 禁止凭空捏造：所有推理只能基于法官宣布的信息和其他玩家的公开发言。
· 禁止让已出局玩家继续参与：已死亡/被票出局玩家不能再发言、投票、夜间讨论或被安排行动。

【本局核心规则】
{build_rules_text(g)}

🔥【极致省字模式（强制指令）】🔥
为模仿真实玩家，你必须遵守以下限制：
1. 💭 内心推理：最多 1-2 条核心逻辑，严格控制在 50 字以内！
2. 🎬 公开发言：干脆利落、直击痛点，像真实网杀一样控制在 80 字以内！不做礼貌寒暄。"""


def build_history_context(g, player):
    """给AI外挂一个'记忆硬盘'，重构带个人视角的绝对时间线"""
    lines = ["\n【你的历史记忆流（按时间先后顺序）】"]
    alive_names = [p.name for p in g.get_alive_players()]
    dead_names = [p.name for p in g.players if not p.alive]
    lines.append(f"当前存活玩家：{', '.join(alive_names) if alive_names else '无'}")
    lines.append(f"已出局玩家：{', '.join(dead_names) if dead_names else '无'}")
    if player.team == "狼人阵营":
        alive_mates = [p.name for p in g.players if p.team == "狼人阵营" and p.alive and p.name != player.name]
        dead_mates = [p.name for p in g.players if p.team == "狼人阵营" and not p.alive and p.name != player.name]
        lines.append(f"当前可与你夜间配合的存活狼队友：{', '.join(alive_mates) if alive_mates else '无'}")
        lines.append(f"已出局狼队友：{', '.join(dead_mates) if dead_mates else '无'}；已出局队友不能再参与讨论或刀人。")
    merged = []
    
    # 1. 抓取法官的公开广播 (必须过滤掉夜晚的神职动作播报，防剧透！)
    for log in g.game_log:
        if log["cls"] in ("sys-phase", "sys-death", "sys-vote"):
            merged.append({"seq": log["seq"], "text": f"📢法官广播: {log['content']}"})
            
    # 2. 抓取玩家的动作和发言
    for act in g.action_feed:
        # 所有人都能听到的白天发言、白天猎人开枪和投票；夜间猎人开枪不直接公开身份
        if act["type"] in ("day_speech", "vote", "vote_hunter_shot"):
            speech_clean = re.sub(r"\{[^}]*\}", "", act["speech"]).strip()
            merged.append({"seq": act["seq"], "text": f"[{act['player']} 公开发言/动作]: {speech_clean}"})
        
        # 自己的私密记忆（防止到了第二天忘了自己昨晚干了啥）
        elif act["player"] == player.name:
            speech_clean = re.sub(r"\{[^}]*\}", "", act["speech"]).strip()
            merged.append({"seq": act["seq"], "text": f"[你({act['player']}) 的私密行动记录]: {speech_clean}"})
        
        # 狼人阵营共享杀人视野
        elif player.team == "狼人阵营" and act["type"] == "night_kill":
            teammate = next((p for p in g.players if p.name == act["player"] and p.team == "狼人阵营"), None)
            if teammate and act["player"] != player.name:
                speech_clean = re.sub(r"\{[^}]*\}", "", act["speech"]).strip()
                teammate_status = "存活狼队友" if teammate.alive else "已出局狼队友的历史记录"
                merged.append({"seq": act["seq"], "text": f"[{teammate_status} {act['player']} 的夜晚密谋]: {speech_clean}"})
                
    merged.sort(key=lambda x: x["seq"])
    
    # sliding window: last 25 events only
    merged = merged[-25:]
    
    # 🚨 斩断空白历史引发的上局幻觉
    if not merged:
        # 检查实际是否有死亡，不能盲目说平安夜
        actual_dead = [p.name for p in g.players if not p.alive]
        if actual_dead:
            lines.append(f"游戏刚刚开始，已知死亡玩家：{', '.join(actual_dead)}。请基于这些信息推理，绝不捏造上一局记录。")
        else:
            lines.append("游戏刚刚开始，大家还互不相识，昨晚是平安夜。绝对不存在任何上一局或前一轮讨论！")
        return "\n".join(lines)
        
    for m in merged:
        lines.append(m["text"])
        
    return "\n".join(lines)


def build_night_context(g, player):
    """构建当前夜晚已知信息"""
    parts = []
    
    if player.role == "狼人":
        alive_mates = [p for p in g.get_players_by_role("狼人") if p.alive and p.name != player.name]
        dead_mates = [p for p in g.players if p.team == "狼人阵营" and not p.alive and p.name != player.name]
        if alive_mates:
            parts.append(f"当前可与你夜间商量的存活狼队友：{', '.join(p.name for p in alive_mates)}")
        else:
            parts.append("当前没有其他存活狼队友，你独自决定今晚刀人。")
        if dead_mates:
            parts.append(f"已出局狼队友：{', '.join(p.name for p in dead_mates)}，他们不能参与今晚讨论或刀人。")
    elif player.role == "女巫":
        if g.wolf_target:
            parts.append(f"今晚被狼人袭击的是：{PLAYER_NAMES[g.wolf_target-1]}")
            parts.append("如果你选择使用解药，请指明要救谁。")
        else:
            parts.append("今晚狼人选择空刀，没有人被袭击。你无需使用解药。")
        parts.append(f"{'你可以使用毒药。' if not g.witch_used_poison else '你已经用过了毒药。'}")
        parts.append(f"{'你可以救人。' if not g.witch_used_save else '你已经用过了解药。'}")
        if g.first_night and g.wolf_target and not g.witch_used_save:
            parts.append("提示：首夜你可以自救。")
    elif player.role == "预言家":
        alive_list = [p.name for p in g.get_alive_players() if p.name != player.name]
        parts.append(f"存活玩家：{', '.join(alive_list)}")
    elif player.role == "守卫":
        alive_list = [p.name for p in g.get_alive_players() if p.name != player.name]
        parts.append(f"存活玩家：{', '.join(alive_list)}")
        if player.last_guarded:
            parts.append(f"你昨晚守护的是{PLAYER_NAMES[player.last_guarded-1]}，今晚不能连续守护同一人。")

    # 🔥 核心：接入上帝视角的真实历史，彻底消灭瞎编幻觉
    parts.append(build_history_context(g, player))
    return "\n".join(parts)


# ── 暂停辅助 ──
async def maybe_pause(g):
    """暂停时在原地等待，不退出协程"""
    while g.stopped:
        await asyncio.sleep(0.1)

async def interruptible_sleep(g, duration, step=0.1):
    """可被停止按钮中断的 sleep：每隔 step 秒检查 g.stopped"""
    elapsed = 0.0
    while elapsed < duration:
        if g.stopped:
            await maybe_pause(g)   # 停止时原地等待，恢复后继续
            return                  # 恢复后不再补剩余时间，直接推进
        await asyncio.sleep(min(step, duration - elapsed))
        elapsed += step

# ── 游戏循环 ──
async def run_game(g, broadcast_callback):

    # ── 开篇仪式：仅首次启动执行 ──
    if not g.ceremony_done:
        g.round = 1
        await broadcast_callback()
        await maybe_pause(g)
        await interruptible_sleep(g, 2)
        g.add_log("🎭 正在随机分配角色...", "system", "sys-phase")
        await broadcast_callback()
        await maybe_pause(g)
        await interruptible_sleep(g, 1.5)
        for p in g.players:
            await maybe_pause(g)
            p.role_revealed = True
            g.add_log(f"🎭 {p.name} 的身份是：{p.role}", "role_assign")
            await broadcast_callback()
            await interruptible_sleep(g, 1.5)
        await maybe_pause(g)
        g.add_log("🌙 天黑了，所有人请闭眼...", "phase", "sys-phase")
        await broadcast_callback()
        await interruptible_sleep(g, 2)
        g.ceremony_done = True

    g.phase = Phase.NIGHT_GUARD

    while True:
        await maybe_pause(g)
        alive = g.get_alive_players()
        wolves = g.get_players_by_role("狼人")
        villagers = g.get_players_by_role("平民")
        gods = [p for p in alive if p.role not in ("狼人", "平民")]

        # ── Check win ──
        alive_wolves = [p for p in wolves if p.alive]
        alive_villagers = [p for p in villagers if p.alive]
        alive_gods = [p for p in gods]

        if not alive_wolves:
            g.phase = Phase.GAME_OVER
            g.add_log("🏆 游戏结束！好人阵营获胜！所有狼人已被消灭。", "system", "sys-phase")
            await broadcast_callback()
            return
        if not alive_villagers:
            g.phase = Phase.GAME_OVER
            g.add_log("🏆 游戏结束！狼人阵营获胜！所有平民已被消灭（屠边）。", "system", "sys-phase")
            await broadcast_callback()
            return
        if not alive_gods:
            g.phase = Phase.GAME_OVER
            g.add_log("🏆 游戏结束！狼人阵营获胜！所有神职已被消灭（屠边）。", "system", "sys-phase")
            await broadcast_callback()
            return

        # ═══════════════════ NIGHT ═══════════════════
        await maybe_pause(g)
        await interruptible_sleep(g, 2)
        g.add_log(f"🌙 第{g.round}晚降临...", "phase", "sys-phase")
        await broadcast_callback()
        await maybe_pause(g)
        await interruptible_sleep(g, 2)

        # Reset night state
        g.guard_target = None
        g.wolf_target = None
        g.witch_save = None
        g.witch_poison = None
        g.seer_target = None
        g.seer_result = None
        g.hunter_target = None
        g.hunter_shot = False

        # ── 1. 守卫行动 ──
        g.phase = Phase.NIGHT_GUARD
        await maybe_pause(g)
        await interruptible_sleep(g, 1.5)
        guards = g.get_players_by_role("守卫")
        if guards:
            g.add_log("🛡️ 守卫请睁眼，请选择你要守护的玩家...", "night", "sys-night")
            await broadcast_callback()
            await interruptible_sleep(g, 1.5)

            guard = guards[0]
            g.add_log(f"⏳ 正在等待 {guard.name} 守护行动...", "night", "sys-night")
            await broadcast_callback()
            ctx = build_night_context(g, guard)
            allowed = [p for p in g.get_alive_players() if p.idx != guard.last_guarded and p.idx != guard.idx]
            target_hint = f"可选目标：{', '.join(p.name for p in allowed)}。你不能守{PLAYER_NAMES[guard.last_guarded-1] if guard.last_guarded else '无'}（不能连守）。" if guard.last_guarded else f"可选目标：{', '.join(p.name for p in g.get_alive_players() if p.name != guard.name)}"
            user_msg = f"{ctx}\n\n现在是第{g.round}晚，你作为守卫需要选择守护一名玩家。\n{target_hint}\n（请发言讨论你的选择，最后用JSON标明：{{\"target\": 号数}}）"
            thinking, speech = await call_ai(build_identity_prompt(g, guard), user_msg, game=g)
            await maybe_pause(g)
            g.add_action(guard.name, "night_guard", thinking, speech)

            # Parse target
            js = parse_action_json(speech + "\n" + thinking)
            if js and isinstance(js, int) and 1 <= js <= g.player_count:
                g.guard_target = js
            else:
                m = re.search(r"(\d+)号", speech)
                if m:
                    g.guard_target = int(m.group(1))
            if g.guard_target == 0:
                g.guard_target = None
            # 强制规则：连守无效，AI 说也没用
            allowed_idxs = {p.idx for p in allowed}
            if g.guard_target and g.guard_target not in allowed_idxs:
                # fallback: 随机守一个合法目标
                if allowed:
                    g.guard_target = random.choice(allowed).idx
                else:
                    g.guard_target = None

            g.add_log("🛡️ 守卫请闭眼。", "night", "sys-night")
            await broadcast_callback()
            await interruptible_sleep(g, 2.5)

        # ── 2. 狼人行动 ──
        g.phase = Phase.NIGHT_WOLF
        await maybe_pause(g)
        await interruptible_sleep(g, 1.5)
        alive_wolves = [p for p in wolves if p.alive]
        if alive_wolves:
            g.add_log("🐺 狼人请睁眼，请商讨你们今晚的击杀目标...", "night", "sys-night")
            await broadcast_callback()
            await interruptible_sleep(g, 2)

            # 严格的一波流循环：不设 while，不纠结是否一致，聊完就强制计票！
            for i, wolf in enumerate(alive_wolves):
                await maybe_pause(g)
                g.add_log(f"🎤 请 {wolf.name} 发表击杀意见...", "night", "sys-night")
                await broadcast_callback()
                ctx = build_night_context(g, wolf)
                prev_speech = ""
                if i > 0:
                    prev = alive_wolves[i-1]
                    prev_action = g.player_actions.get(prev.name, {}).get("night_kill", {})
                    prev_msg = prev_action.get("speech", "")
                    if prev_msg:
                        prev_speech = f"\n\n你的队友{prev.name}说：\"{prev_msg}\""

                targets = [p for p in g.get_alive_players() if p.team != "狼人"]
                user_msg = f"{ctx}{prev_speech}\n\n讨论目标：你和队友需要选择今晚击杀谁。\n可选目标：{', '.join(p.name for p in targets)}\n（请发言讨论你的选择，最后用JSON标明：{{\"target\": 号数或0表示空刀}}）"
                
                thinking, speech = await call_ai(build_identity_prompt(g, wolf), user_msg, game=g)
                await maybe_pause(g)
                g.add_action(wolf.name, "night_kill", thinking, speech)
                await broadcast_callback()
                await interruptible_sleep(g, 2.5)

            # 直接收集票型并决定死者，绝不让狼人重新讨论
            wolf_votes = []
            for w in alive_wolves:
                wa = g.player_actions.get(w.name, {}).get("night_kill", {})
                js = parse_action_json(get_action_parse_text(wa))
                v = 0
                if js and isinstance(js, int) and 0 <= js <= g.player_count:
                    v = js
                else:
                    m = re.search(r"(\d+)号", wa.get("raw_speech", wa.get("speech", "")))
                    if m:
                        v = int(m.group(1))
                wolf_votes.append(v)
                
            from collections import Counter
            valid_votes = [v for v in wolf_votes if v == 0 or (v and v not in [w.idx for w in alive_wolves])]
            vote_counts = Counter(valid_votes)
            
            if vote_counts:
                top_vote = vote_counts.most_common(1)[0][0]
                g.wolf_target = top_vote if top_vote != 0 else None
            else:
                g.wolf_target = None

            g.add_log("🐺 狼人请闭眼。", "night", "sys-night")
            await broadcast_callback()
            await interruptible_sleep(g, 2)

        await broadcast_callback()
        await interruptible_sleep(g, 2)

        # ── 3. 女巫行动 ──
        g.phase = Phase.NIGHT_WITCH
        await maybe_pause(g)
        await interruptible_sleep(g, 1.5)
        witches = g.get_players_by_role("女巫")
        if witches:
            g.add_log("💊 女巫请睁眼...", "night", "sys-night")
            await broadcast_callback()
            await interruptible_sleep(g, 1.5)

            witch = witches[0]
            g.add_log(f"⏳ 正在等待 {witch.name} 决定用药...", "night", "sys-night")
            await broadcast_callback()
            ctx = build_night_context(g, witch)
            if not g.wolf_target:
                action_prompt = "今晚无人被狼人袭击，你不能使用解药。请决定是否使用毒药。" if not g.witch_used_poison else "你已用完所有药或今晚无药可用。"
            else:
                action_prompt = "你有一瓶解药和一瓶毒药。请决定是否救人、是否毒人。" if not g.witch_used_save and not g.witch_used_poison else '你只有一瓶毒药可用。' if g.witch_used_save else '你只有一瓶解药可用。' if g.witch_used_poison else '你已用完所有药。'
            user_msg = f"{ctx}\n\n你的选择：\n{action_prompt}\n（请发言，最后用JSON标明：{{\"save\": 号数或0, \"poison\": 号数或0}}。注：同一晚不能同时用两瓶药。）"
            thinking, speech = await call_ai(build_identity_prompt(g, witch), user_msg, game=g)
            await maybe_pause(g)
            g.add_action(witch.name, "night_witch", thinking, speech)
            save_t, poison_t = parse_witch_json(speech + "\n" + thinking)

            if save_t is None or poison_t is None:
                # Fallback: regex
                save_m = re.search(r"(?:解药|救|救下|救活|捞|奶)[^0-9]*(\d+)号", speech)
                poison_m = re.search(r"(?:毒药|毒杀|毒|撒毒)[^0-9]*(\d+)号", speech)
                save_denied = re.search(r"(不救|不使用解药|不用解药|不救人)", speech)
                poison_denied = re.search(r"(不毒|不使用毒药|不用毒药|不毒人)", speech)
                if save_m and not save_denied:
                    save_t = int(save_m.group(1))
                elif g.wolf_target and re.search(r"(使用解药|救他|决定救|用解药|救下)", speech):
                    save_t = g.wolf_target  # 智能代词推断：女巫说"救他"即救狼人目标
                if poison_m and not poison_denied:
                    poison_t = int(poison_m.group(1))

            if save_t and save_t == g.wolf_target and not g.witch_used_save:
                g.witch_save = save_t
                g.witch_used_save = True
                # 狼人空刀或目标不匹配时，解药不消耗
            if poison_t and not g.witch_used_poison:
                if not g.witch_save:  # 判断当晚是否已用解药，而非历史记录
                    g.witch_poison = poison_t
                    g.witch_used_poison = True
                # 同晚已用救药则不能再用毒药

            g.add_log("💊 女巫请闭眼。", "night", "sys-night")
            await broadcast_callback()
            await interruptible_sleep(g, 2.5)

        # ── 4. 预言家行动 ──
        g.phase = Phase.NIGHT_SEER
        await maybe_pause(g)
        await interruptible_sleep(g, 1.5)
        seers = g.get_players_by_role("预言家")
        if seers:
            g.add_log("🔮 预言家请睁眼，请选择你要查验的玩家...", "night", "sys-night")
            await broadcast_callback()
            await interruptible_sleep(g, 1.5)

            seer = seers[0]
            g.add_log(f"⏳ 正在等待 {seer.name} 查验身份...", "night", "sys-night")
            await broadcast_callback()
            ctx = build_night_context(g, seer)
            targets = [p for p in g.get_alive_players() if p.name != seer.name]
            user_msg = f"{ctx}\n\n现在是第{g.round}晚，你作为预言家可以选择查验一名玩家的身份。\n可选目标：{', '.join(p.name for p in targets)}\n（请发言，最后用JSON标明：{{\"target\": 号数}}）"
            thinking, speech = await call_ai(build_identity_prompt(g, seer), user_msg, game=g)
            await maybe_pause(g)
            g.add_action(seer.name, "night_seer", thinking, speech)
            js = parse_action_json(speech + "\n" + thinking)
            if js and isinstance(js, int) and 1 <= js <= g.player_count:
                g.seer_target = js
            else:
                m = re.search(r"(\d+)号", speech)
                if m:
                    g.seer_target = int(m.group(1))
            if g.seer_target and 1 <= g.seer_target <= g.player_count:
                target_player = g.players[g.seer_target-1]
                g.seer_result = "狼人" if target_player.role == "狼人" else "好人"
                g.add_action(seer.name, "night_seer_result", f"查验{target_player.name}：{g.seer_result}", f"🔮 {target_player.name} 的身份是：{g.seer_result}")
                await broadcast_callback()
                await interruptible_sleep(g, 1.5)
            g.add_log("🔮 预言家请闭眼。", "night", "sys-night")
            await broadcast_callback()
            await interruptible_sleep(g, 2.5)

        # ── 记录守卫昨晚目标(不能连守) ──
        guards = g.get_players_by_role("守卫")
        if guards and g.guard_target:
            guards[0].last_guarded = g.guard_target

        # ── Resolve Night Deaths ──
        await interruptible_sleep(g, 2)
        dead_set = set()

        # 守卫保护
        guarded = g.guard_target
        # 狼人击杀
        wolf_kill = g.wolf_target
        # 女巫拯救
        witch_saved = g.witch_save
        # 女巫毒杀
        witch_poisoned = g.witch_poison

        # 同守同救检测
        if wolf_kill and witch_saved and wolf_kill == witch_saved == guarded:
            # 同守同救 → 死亡
            g.add_log(f"⚖️ {PLAYER_NAMES[wolf_kill-1]} 同时被守卫守护和女巫解药救起，按同守同救规则仍会死亡。", "night", "sys-night")
            dead_set.add(wolf_kill)
        elif wolf_kill and guarded and wolf_kill == guarded:
            # 守护成功，狼人没杀到
            g.add_log(f"🛡️ 守卫守护生效，{PLAYER_NAMES[wolf_kill-1]} 没有被狼人杀死。", "night", "sys-night")
            pass
        elif wolf_kill and witch_saved and wolf_kill == witch_saved:
            # 女巫救了
            g.add_log(f"💊 女巫使用了解药。", "night", "sys-night")
        elif wolf_kill:
            dead_set.add(wolf_kill)

        if witch_poisoned:
            dead_set.add(witch_poisoned)

        # 猎人开枪
        hunter_dead = [p for p in g.players if p.alive and p.idx in dead_set and p.role == "猎人" and p.idx != witch_poisoned]
        for h in hunter_dead:
            # 静默结算：半夜不广播猎人身份和开枪（防止剧透），直接问目标
            await broadcast_callback()
            await interruptible_sleep(g, 2)
            # Get hunter's target from action
            alive_targets = [p for p in g.get_alive_players() if p.idx != h.idx and p.idx not in dead_set]
            hunter_prompt = f"猎人{PLAYER_NAMES[h.idx-1]}，你被杀害了！你可以开枪带走一名玩家。\n存活玩家：{', '.join(p.name for p in alive_targets)}\n（最后用JSON标明：{{\"target\": 号数或0表示不开枪}}）"
            thinking, speech = await call_ai(f"你是猎人{PLAYER_NAMES[h.idx-1]}，你刚被杀害。", hunter_prompt, game=g)
            await maybe_pause(g)
            g.add_action(h.name, "night_hunter_shot", thinking, speech)
            js = parse_action_json(speech + "\n" + thinking)
            ht = 0
            if js and isinstance(js, int) and 0 <= js <= g.player_count:
                ht = js
            else:
                m = re.search(r"(\d+)号", speech)
                if m:
                    ht = int(m.group(1))
            if ht and ht not in dead_set and ht != h.idx and g.players[ht-1].alive:
                dead_set.add(ht)

        # 宣布死亡
        if dead_set:
            for d in sorted(dead_set):
                g.players[d-1].alive = False
                g.add_log(f"📢 {PLAYER_NAMES[d-1]} 昨晚去世了", "death", "sys-death")
                await broadcast_callback()
                await interruptible_sleep(g, 1.5)
        else:
            g.add_log("📢 昨晚是平安夜！", "death", "sys-death")

        g.first_night = False
        g.round += 1
        await broadcast_callback()
        await interruptible_sleep(g, 3)

        # ═══════════════════ DAY ═══════════════════
        alive = g.get_alive_players()
        if len(alive) <= 2:
            continue  # Will hit win check at top

        g.phase = Phase.DAY_DISCUSSION
        await maybe_pause(g)
        g.add_log(f"☀️ 第{g.round-1}天，天亮了。开始白天讨论。", "phase", "sys-phase")
        await broadcast_callback()
        await interruptible_sleep(g, 3)

        # ── 白天发言 ──
        for p in alive:
            await maybe_pause(g)
            g.add_log(f"🎤 请 {p.name} 发言...", "phase", "sys-phase")
            await broadcast_callback()
            known_info = build_history_context(g, p)
            dead_names = [x.name for x in g.players if not x.alive]
            if dead_names:
                dead_status = f"【系统强制提醒：已死亡出局的玩家有 {', '.join(dead_names)}】"
            else:
                dead_status = "【系统强制提醒：昨晚是平安夜，无人死亡】"
            user_msg = f"{known_info}\n\n{dead_status}\n现在是白天自由讨论时间。请严格根据上面提醒的死讯（绝不能自己凭空捏造平安夜）和大家的发言进行推理，你怀疑谁是狼人？\n（请发言，最后用JSON标明：{{\"target\": 你怀疑的号数或0}}）"
            thinking, speech = await call_ai(build_identity_prompt(g, p), user_msg, game=g)
            await maybe_pause(g)
            g.add_action(p.name, "day_speech", thinking, speech)
            await broadcast_callback()
            await interruptible_sleep(g, 4)

        # ── 投票 ──
        g.phase = Phase.DAY_VOTE
        await maybe_pause(g)
        await interruptible_sleep(g, 2)
        g.add_log("🗳️ 开始投票！", "phase", "sys-phase")
        await broadcast_callback()
        await interruptible_sleep(g, 2)

        votes = {}
        alive = g.get_alive_players()
        for p in alive:
            await maybe_pause(g)
            g.add_log(f"🗳️ 正在等待 {p.name} 投票...", "vote", "sys-vote")
            await broadcast_callback()
            targets = [x for x in alive if x.name != p.name]
            known_info = build_history_context(g, p)
            dead_names = [x.name for x in g.players if not x.alive]
            if dead_names:
                dead_status = f"【系统强制提醒：已死亡出局的玩家有 {', '.join(dead_names)}】"
            else:
                dead_status = "【系统强制提醒：昨晚是平安夜，无人死亡】"
            user_msg = f"{known_info}\n\n{dead_status}\n现在是投票环节！请基于刚才白天的发言讨论，投票选出你最怀疑的一人放逐。\n可选目标：{', '.join(x.name for x in targets)}\n（最后用JSON标明：{{\"vote\": 号数}}。投票是强制性的，必须选一个人！）"
            thinking, speech = await call_ai(build_identity_prompt(g, p), user_msg, game=g)
            await maybe_pause(g)
            js = parse_action_json(speech + "\n" + thinking)
            vote = 0
            if js and isinstance(js, int) and 1 <= js <= g.player_count:
                vote = js
            else:
                m = re.search(r"(\d+)号", speech)
                if m:
                    vote = int(m.group(1))
            valid_vote = bool(vote and 1 <= vote <= g.player_count and g.players[vote-1].alive and vote != p.idx)
            display_speech = speech
            if not clean_public_speech(display_speech):
                display_speech = f"我投{PLAYER_NAMES[vote-1]}。" if valid_vote else "本轮没有有效投票。"
            g.add_action(p.name, "vote", thinking, display_speech, {"vote_target": vote if valid_vote else 0})
            if valid_vote:
                votes[p.name] = vote
            await broadcast_callback()
            await interruptible_sleep(g, 2)
    
        # Count votes
        from collections import Counter
        vote_counter = Counter(votes.values())
        if vote_counter:
            max_votes = vote_counter.most_common(1)[0][1]
            top = [k for k, v in vote_counter.items() if v == max_votes]
            eliminated = random.choice(top) if len(top) > 1 else top[0]
            voted_out = g.players[eliminated-1]
            voted_out.alive = False
            g.add_log(f"🗳️ {voted_out.name} 被投票出局！", "vote", "sys-vote")
    
            # If hunter voted out, can shoot
            if voted_out.role == "猎人":
                await interruptible_sleep(g, 2)
                alive_targets = [p for p in g.get_alive_players() if p.name != voted_out.name]
                if alive_targets:
                    h_prompt = f"猎人{voted_out.name}，你被投票出局了！你可以开枪带走一名玩家。\n存活玩家：{', '.join(p.name for p in alive_targets)}\n（最后用JSON标明：{{\"target\": 号数或0表示不开枪}}）"
                    thinking, speech = await call_ai(f"你是猎人{voted_out.name}，你被投票出局。", h_prompt, game=g)
                    await maybe_pause(g)
                    g.add_action(voted_out.name, "vote_hunter_shot", thinking, speech)
                    js = parse_action_json(speech + "\n" + thinking)
                    ht = 0
                    if js and isinstance(js, int) and 0 <= js <= g.player_count:
                        ht = js
                    else:
                        m = re.search(r"(\d+)号", speech)
                        if m:
                            ht = int(m.group(1))
                    if ht and 1 <= ht <= g.player_count and g.players[ht-1].alive and ht != eliminated:
                        g.players[ht-1].alive = False
                        g.add_log(f"🏹 {PLAYER_NAMES[ht-1]} 被猎人开枪带走！", "death", "sys-death")
    
            await broadcast_callback()
            await interruptible_sleep(g, 2)
    
        await interruptible_sleep(g, 2)
        # Next night


