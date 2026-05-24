"""Add judge commentary to all four night roles."""
import re

with open('game_engine.py', 'r', encoding='utf-8') as f:
    c = f.read()

changes = 0

# 1. Guard open
old = '        if guards:\n            guard = guards[0]'
new = '        if guards:\n            g.add_log("🛡️ 守卫请睁眼，请选择你要守护的玩家...", "night", "sys-night")\n            await broadcast_callback()\n            await interruptible_sleep(g, 1.5)\n\n            guard = guards[0]'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('1. Guard open')

# 2. Guard close
old = 'g.add_log(f"🛡️ {guard.name} 正在守护...", "night", "sys-night")'
new = 'g.add_log("🛡️ 守卫请闭眼。", "night", "sys-night")'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('2. Guard close')
else:
    print(f'2. FAILED - trying unicode variant')
    old2 = 'g.add_log(f\"\U0001f6e1\ufe0f {guard.name} 正在守护...\", \"night\", \"sys-night\")'
    if old2 in c:
        c = c.replace(old2, new)
        changes += 1
        print('2. Guard close (unicode)')

# 3. Wolf open
old = 'g.add_log("🐺 狼人正在密谋...", "night", "sys-night")'
new = 'g.add_log("🐺 狼人请睁眼，请商讨你们今晚的击杀目标...", "night", "sys-night")'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('3. Wolf open')

# 4. Wolf close
old = '            else:\n                g.wolf_target = None  # 无人决定则默认空刀'
new = '            else:\n                g.wolf_target = None\n\n            g.add_log("🐺 狼人请闭眼。", "night", "sys-night")\n            await broadcast_callback()\n            await interruptible_sleep(g, 2)'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('4. Wolf close')

# 5. Witch open
old = '        if witches:\n            witch = witches[0]'
new = '        if witches:\n            g.add_log("💊 女巫请睁眼...", "night", "sys-night")\n            await broadcast_callback()\n            await interruptible_sleep(g, 1.5)\n\n            witch = witches[0]'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('5. Witch open')

# 6. Witch close
old = 'g.add_log("💊 女巫在药剂前沉思...", "night", "sys-night")'
new = 'g.add_log("💊 女巫请闭眼。", "night", "sys-night")'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('6. Witch close')

# 7. Seer open
old = '        if seers:\n            seer = seers[0]'
new = '        if seers:\n            g.add_log("🔮 预言家请睁眼，请选择你要查验的玩家...", "night", "sys-night")\n            await broadcast_callback()\n            await interruptible_sleep(g, 1.5)\n\n            seer = seers[0]'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('7. Seer open')

# 8. Seer close
old = 'g.add_log("🔮 预言家正在查验...", "night", "sys-night")'
new = 'g.add_log("🔮 预言家请闭眼。", "night", "sys-night")'
if old in c:
    c = c.replace(old, new)
    changes += 1
    print('8. Seer close')

with open('game_engine.py', 'w', encoding='utf-8') as f:
    f.write(c)

print(f'\nDone: {changes}/8 changes')
