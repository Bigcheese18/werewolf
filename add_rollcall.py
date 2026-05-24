"""Add judge roll-call messages before each AI call."""
with open('game_engine.py', 'r', encoding='utf-8') as f:
    c = f.read()

changes = 0

# 1. Guard roll-call: after guard = guards[0], before ctx = build_night_context
old = 'guard = guards[0]\n            ctx = build_night_context(g, guard)'
new = 'guard = guards[0]\n            g.add_log(f"⏳ 正在等待 {guard.name} 守护行动...", "night", "sys-night")\n            await broadcast_callback()\n            ctx = build_night_context(g, guard)'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('1. Guard roll-call')

# 2. Wolf roll-call: after if g.stopped: return / await maybe_pause(g), before ctx
old = 'if g.stopped: return\n                ctx = build_night_context(g, wolf)'
new = 'if g.stopped: return\n                g.add_log(f"🎤 请 {wolf.name} 发表击杀意见...", "night", "sys-night")\n                await broadcast_callback()\n                ctx = build_night_context(g, wolf)'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('2. Wolf roll-call')
else:
    print('2. FAILED - pattern not found')

# 3. Witch roll-call: after witch = witches[0], before ctx
old = 'witch = witches[0]\n            ctx = build_night_context(g, witch)'
new = 'witch = witches[0]\n            g.add_log(f"⏳ 正在等待 {witch.name} 决定用药...", "night", "sys-night")\n            await broadcast_callback()\n            ctx = build_night_context(g, witch)'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('3. Witch roll-call')

# 4. Seer roll-call: after seer = seers[0], before ctx
old = 'seer = seers[0]\n            ctx = build_night_context(g, seer)'
new = 'seer = seers[0]\n            g.add_log(f"⏳ 正在等待 {seer.name} 查验身份...", "night", "sys-night")\n            await broadcast_callback()\n            ctx = build_night_context(g, seer)'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('4. Seer roll-call')

with open('game_engine.py', 'w', encoding='utf-8') as f:
    f.write(c)
print(f'\nDone: {changes}/4')
