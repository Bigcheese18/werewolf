"""SOCKS5 TCP 转发器 — 把本地端口流量通过 SOCKS5 代理发到目标服务器"""
import asyncio, struct, socket, sys

SOCKS5_PROXY = ('127.0.0.1', 10808)

async def socks5_connect(host, port):
    r, w = await asyncio.open_connection(*SOCKS5_PROXY)
    w.write(bytes([0x05, 0x01, 0x00]))
    await w.drain()
    resp = await r.read(2)
    assert resp == bytes([0x05, 0x00])
    ip = socket.gethostbyname(host)
    req = bytes([0x05, 0x01, 0x00, 0x01]) + socket.inet_aton(ip) + struct.pack('>H', port)
    w.write(req)
    await w.drain()
    resp = await r.read(10)
    assert resp[1] == 0x00, f"SOCKS5 connect refused: {resp.hex()}"
    return r, w

async def pipe(a, b, name=""):
    try:
        while True:
            data = await a.read(65536)
            if not data:
                break
            b.write(data)
            await b.drain()
    except Exception as e:
        if not isinstance(e, asyncio.CancelledError):
            pass
    finally:
        try: a.close()
        except: pass
        try: b.close()
        except: pass

async def handle_client(local_reader, local_writer, target_host, target_port):
    try:
        remote_reader, remote_writer = await socks5_connect(target_host, target_port)
        t1 = asyncio.create_task(pipe(local_reader, remote_writer, "local->remote"))
        t2 = asyncio.create_task(pipe(remote_reader, local_writer, "remote->local"))
        done, _ = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
        for t in [t1, t2]:
            t.cancel()
    except Exception as e:
        print(f"[relay] Error: {e}")
        try: local_writer.close()
        except: pass

async def main():
    listen_port = int(sys.argv[1]) if len(sys.argv) > 1 else 17835
    target_host = sys.argv[2] if len(sys.argv) > 2 else "bore.pub"
    target_port = int(sys.argv[3]) if len(sys.argv) > 3 else 7835
    
    server = await asyncio.start_server(
        lambda r, w: handle_client(r, w, target_host, target_port),
        '127.0.0.1', listen_port
    )
    print(f"[relay] SOCKS5 relay: 127.0.0.1:{listen_port} → {target_host}:{target_port} (via proxy)")
    
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
