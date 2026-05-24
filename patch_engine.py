"""Apply all game_engine.py changes in one batch."""
import re

with open('game_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

counts = []

# Helper: count-success replace
def rep(old, new, label):
    global content
    n = content.count(old)
    content = content.replace(old, new)
    counts.append(f'{label}: {n}→{content.count(new)}')
    return n > 0

# 1. GameState.player_count
rep(
    '    player_configs: dict = field(default_factory=dict)  # 玩家专属 API 配置 {name: {model, api_key, api_base}}',
    '    player_configs: dict = field(default_factory=dict)\n    player_count: int = 12',
    '1.player_count field')

# 2. to_dict
rep('"player_configs": self.player_configs,',
    '"player_configs": self.player_configs,\n            "player_count": self.player_count,',
    '2.to_dict')

# 3. init_game
old = '''def init_game():
    g = GameState()
    roles = ROLE_POOL[:]
    random.shuffle(roles)
    for i in range(12):
        role = roles[i]
        g.players.append(Player(
            idx=i+1, name=PLAYER_NAMES[i],
            role=role, team=ROLE_TEAM[role],
        ))
    g.add_log("🎮 12人标准局狼人杀即将开始！", "system", "sys-phase")
    g.game_token = random.randint(100000, 999999)
    return g'''
new = '''def init_game(player_count=12):
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
    return g'''
rep(old, new, '3.init_game')

# 4. build_identity_prompt(g, player)
rep('def build_identity_prompt(player):', 'def build_identity_prompt(g, player):', '4.build_identity_prompt sig')

# 5. prompt text
rep('12人标准狼人杀游戏', '{g.player_count}人狼人杀游戏', '5.prompt text')

# 6. build_identity_prompt calls
for name in ['p', 'guard', 'wolf', 'witch', 'seer']:
    rep(f'build_identity_prompt({name})', f'build_identity_prompt(g, {name})', f'6.call {name}')

# 7. 12→g.player_count
n12 = len(re.findall(r'(?<!\w)1 <= js <= 12(?!\w)', content))
content = re.sub(r'(?<!\w)1 <= js <= 12(?!\w)', '1 <= js <= g.player_count', content)
n02 = len(re.findall(r'(?<!\w)0 <= js <= 12(?!\w)', content))
content = re.sub(r'(?<!\w)0 <= js <= 12(?!\w)', '0 <= js <= g.player_count', content)
counts.append(f'7.12 bounds: {n12}+{n02}')

# 8. interruptible_sleep in run_game
rg = content.find('async def run_game(g, broadcast_callback):')
before = content[:rg]
after = content[rg:]
n = len(re.findall(r'(?<!interruptible_)asyncio\.sleep\(\d+\.?\d*\)', after))
after = re.sub(r'(?<!interruptible_)asyncio\.sleep\((\d+\.?\d*)\)', r'interruptible_sleep(g, \1)', after)
content = before + after
counts.append(f'8.interruptible_sleep: {n}')

# 9. if g.stopped: return → maybe_pause
rep('if g.stopped: return', 'await maybe_pause(g)', '9.stopped→pause')

# 10. Judge open/close
rep('        if guards:\n            guard = guards[0]',
    '        if guards:\n            g.add_log("🛡️ 守卫请睁眼，请选择你要守护的玩家...", "night", "sys-night")\n            await broadcast_callback()\n            await interruptible_sleep(g, 1.5)\n\n            guard = guards[0]',
    '10a.guard open')
rep('g.add_log(f"🛡️ {guard.name} 正在守护...", "night", "sys-night")',
    'g.add_log("🛡️ 守卫请闭眼。", "night", "sys-night")', '10b.guard close')
rep('g.add_log("🐺 狼人正在密谋...", "night", "sys-night")',
    'g.add_log("🐺 狼人请睁眼，请商讨你们今晚的击杀目标...", "night", "sys-night")', '10c.wolf open')
rep('            else:\n                g.wolf_target = None  # 无人决定则默认空刀',
    '            else:\n                g.wolf_target = None\n\n            g.add_log("🐺 狼人请闭眼。", "night", "sys-night")\n            await broadcast_callback()\n            await interruptible_sleep(g, 2)',
    '10d.wolf close')
rep('        if witches:\n            witch = witches[0]',
    '        if witches:\n            g.add_log("💊 女巫请睁眼...", "night", "sys-night")\n            await broadcast_callback()\n            await interruptible_sleep(g, 1.5)\n\n            witch = witches[0]',
    '10e.witch open')
rep('g.add_log("💊 女巫在药剂前沉思...", "night", "sys-night")',
    'g.add_log("💊 女巫请闭眼。", "night", "sys-night")', '10f.witch close')
rep('        if seers:\n            seer = seers[0]',
    '        if seers:\n            g.add_log("🔮 预言家请睁眼，请选择你要查验的玩家...", "night", "sys-night")\n            await broadcast_callback()\n            await interruptible_sleep(g, 1.5)\n\n            seer = seers[0]',
    '10g.seer open')
rep('g.add_log("🔮 预言家正在查验...", "night", "sys-night")',
    'g.add_log("🔮 预言家请闭眼。", "night", "sys-night")', '10h.seer close')

# 11. Roll-call
rep('guard = guards[0]\n            ctx = build_night_context(g, guard)',
    'guard = guards[0]\n            g.add_log(f"⏳ 正在等待 {guard.name} 守护行动...", "night", "sys-night")\n            await broadcast_callback()\n            ctx = build_night_context(g, guard)',
    '11a.guard roll')
rep('await maybe_pause(g)\n                ctx = build_night_context(g, wolf)',
    'await maybe_pause(g)\n                g.add_log(f"🎤 请 {wolf.name} 发表击杀意见...", "night", "sys-night")\n                await broadcast_callback()\n                ctx = build_night_context(g, wolf)',
    '11b.wolf roll')
rep('witch = witches[0]\n            ctx = build_night_context(g, witch)',
    'witch = witches[0]\n            g.add_log(f"⏳ 正在等待 {witch.name} 决定用药...", "night", "sys-night")\n            await broadcast_callback()\n            ctx = build_night_context(g, witch)',
    '11c.witch roll')
rep('seer = seers[0]\n            ctx = build_night_context(g, seer)',
    'seer = seers[0]\n            g.add_log(f"⏳ 正在等待 {seer.name} 查验身份...", "night", "sys-night")\n            await broadcast_callback()\n            ctx = build_night_context(g, seer)',
    '11d.seer roll')
rep('await maybe_pause(g)\n            known_info = build_history_context(g, p)',
    'await maybe_pause(g)\n            g.add_log(f"🎤 请 {p.name} 发言...", "phase", "sys-phase")\n            await broadcast_callback()\n            known_info = build_history_context(g, p)',
    '11e.day roll')
rep('await maybe_pause(g)\n            targets = [x for x in alive if x.name != p.name]',
    'await maybe_pause(g)\n            g.add_log(f"🗳️ 正在等待 {p.name} 投票...", "vote", "sys-vote")\n            await broadcast_callback()\n            targets = [x for x in alive if x.name != p.name]',
    '11f.vote roll')

# 12. Death status
rep('user_msg = f"{known_info}\\n\\n现在是白天自由讨论时间。请仔细结合前面其他人的发言',
    'dead_names = [x.name for x in g.players if not x.alive]\n            dead_status = f"【系统强制提醒：已死亡出局的玩家有 {\', \'.join(dead_names)}】" if dead_names else "【系统强制提醒：昨晚是平安夜，无人死亡】"\n            user_msg = f"{known_info}\\n\\n{dead_status}\\n现在是白天自由讨论时间。请严格根据上面的死亡名单（绝不能凭空捏造谁死了或平安夜），结合大家发言推理谁可能是狼人。',
    '12a.day death')
rep('user_msg = f"{known_info}\\n\\n现在是投票环节！请基于刚才白天的发言讨论，投票选出你最怀疑的一人放逐。',
    'dead_names = [x.name for x in g.players if not x.alive]\n            dead_status = f"【系统强制提醒：已死亡出局的玩家有 {\', \'.join(dead_names)}】" if dead_names else "【系统强制提醒：昨晚是平安夜，无人死亡】"\n            user_msg = f"{known_info}\\n\\n{dead_status}\\n现在是投票环节！请基于刚才白天的发言讨论，投票选出你最怀疑的一人放逐。',
    '12b.vote death')

# 13. Sliding window
rep('merged.sort(key=lambda x: x["seq"])\n    \n    if not merged:',
    'merged.sort(key=lambda x: x["seq"])\n    \n    merged = merged[-25:]\n    \n    if not merged:',
    '13.sliding window')

# 14. Word limit
rep('· 禁止凭空捏造：所有推理只能基于法官宣布的信息和其他玩家的公开发言。"""',
    '· 禁止凭空捏造：所有推理只能基于法官宣布的信息和其他玩家的公开发言。\n\n🔥【极致省字模式（强制指令）】🔥\n为模仿真实玩家，你必须遵守以下限制：\n1. 💭 内心推理：最多 1-2 条核心逻辑，严格控制在 50 字以内！\n2. 🎬 公开发言：干脆利落、直击痛点，像真实网杀一样控制在 80 字以内！不做礼貌寒暄。"""',
    '14.word limit')

with open('game_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('\n'.join(counts))
print('DONE')
