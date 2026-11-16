"""Phone-width check of a page with Microsoft Edge over the DevTools protocol (standard library only).

python scripts/phone_check.py <url> <out.png> [--dark] [--wait-js EXPR] [--click-js EXPR --after-js EXPR]
                               [--width W --height H --desktop] [--report-js EXPR] [--first-screen out2.png]
Emulates a 390 x 844 CSS px phone (device pixel ratio 2, mobile, touch) in headless Edge, waits until EXPR is true
(the page's own JavaScript has run), optionally runs a click script and waits for a second condition, then prints
the viewport width, the document's scrollWidth and every element that sticks out of the viewport outside a
scrolling container, and saves a full-page screenshot (at most 9000 px tall). Used for the live demo (space/app.py)
and the recorded-answer viewer (demo/viewer/index.html); Edge's own --screenshot cannot go below its minimum window
width, which made a 390 px capture look clipped.
--width / --height set another viewport (CSS px); --desktop drops the mobile, touch and device-pixel-ratio-2
emulation (a laptop window, e.g. --width 1366 --height 768 --desktop). --report-js prints the value of EXPR after
loading (e.g. the bottom of an element in CSS px); --first-screen also saves the viewport alone, before scrolling.
"""
import base64, json, os, shutil, socket, struct, subprocess, sys, tempfile, time, urllib.request

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
args = sys.argv[1:]
url, out = args[0], args[1]
dark = "--dark" in args
def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default
wait_js = opt("--wait-js", "document.readyState === 'complete'")
click_js, after_js = opt("--click-js"), opt("--after-js")
W, H = int(opt("--width", 390)), int(opt("--height", 844))
desktop = "--desktop" in args
report_js, first_screen = opt("--report-js"), opt("--first-screen")
port = 9333 + os.getpid() % 500
prof = tempfile.mkdtemp(prefix="edgecdp")
proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", f"--remote-debugging-port={port}",
                         f"--user-data-dir={prof}", "--no-first-run", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(100):
        try:
            tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1).read())
            ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
            break
        except Exception:
            time.sleep(0.2)
    host_port, path = ws_url[len("ws://"):].split("/", 1)
    h, p = host_port.split(":")
    s = socket.create_connection((h, int(p)))
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        buf += s.recv(4096)
    rest = buf.split(b"\r\n\r\n", 1)[1]

    def recv_exact(n):
        nonlocal_buf = recv_exact.buf
        while len(nonlocal_buf) < n:
            nonlocal_buf += s.recv(1 << 20)
        recv_exact.buf = nonlocal_buf[n:]
        return nonlocal_buf[:n]
    recv_exact.buf = rest

    def send(obj):
        data = json.dumps(obj).encode()
        hdr = bytearray([0x81])
        n = len(data)
        if n < 126:
            hdr.append(0x80 | n)
        elif n < 65536:
            hdr.append(0x80 | 126); hdr += struct.pack(">H", n)
        else:
            hdr.append(0x80 | 127); hdr += struct.pack(">Q", n)
        mask = os.urandom(4)
        hdr += mask
        s.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv():
        msg = b""
        while True:
            b1, b2 = recv_exact(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", recv_exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", recv_exact(8))[0]
            msg += recv_exact(n)
            if b1 & 0x80:
                return json.loads(msg)

    ids = iter(range(1, 10**6))
    def call(method, **params):
        i = next(ids)
        send({"id": i, "method": method, "params": params})
        while True:
            m = recv()
            if m.get("id") == i:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})

    def ev(expr):
        r = call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    call("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=1 if desktop else 2, mobile=not desktop)
    call("Emulation.setTouchEmulationEnabled", enabled=not desktop)
    call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "dark" if dark else "light"}])
    call("Page.enable")
    call("Page.navigate", url=url)

    def wait(expr, t=90):
        t0 = time.time()
        while time.time() - t0 < t:
            try:
                if ev(expr):
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False
    ok = wait(wait_js)
    time.sleep(1.5)
    if click_js:
        ev(click_js)
        ok = wait(after_js, 600) and ok
        time.sleep(1.0)
    metrics = ev("""(() => {
      const vw = document.documentElement.clientWidth, wide = [];
      for (const el of document.querySelectorAll('body *')) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && (r.right > vw + 1 || r.left < -1)) {
          let anc = el.parentElement, clipped = false;
          while (anc) { const o = getComputedStyle(anc).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') { clipped = true; break; } anc = anc.parentElement; }
          if (!clipped) wide.push(el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ').slice(0,2).join('.') : '') + ' ' + Math.round(r.left) + '..' + Math.round(r.right));
        }
      }
      return {viewport: vw, scrollWidth: document.documentElement.scrollWidth, bodyScrollWidth: document.body.scrollWidth,
              height: document.documentElement.scrollHeight, wide: wide.slice(0, 25), n_wide: wide.length};
    })()""")
    if report_js:
        metrics["report"] = ev(report_js)
    print(json.dumps({"loaded": ok, "window": [W, H], **metrics}, indent=1))
    if first_screen:
        shot = call("Page.captureScreenshot", format="png")
        open(first_screen, "wb").write(base64.b64decode(shot["data"]))
        print("saved", first_screen)
    h = min(int(metrics["height"]), 9000)
    call("Emulation.setDeviceMetricsOverride", width=W, height=h, deviceScaleFactor=1, mobile=not desktop)
    time.sleep(0.8)
    shot = call("Page.captureScreenshot", format="png", captureBeyondViewport=True)
    open(out, "wb").write(base64.b64decode(shot["data"]))
    print("saved", out)
finally:
    # Edge hands off to processes outside the launcher's tree: stop every msedge.exe started with this profile
    proc.kill()
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine -like '*"
          + os.path.basename(prof) + "*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
          "-ErrorAction SilentlyContinue }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
    time.sleep(1)
    shutil.rmtree(prof, ignore_errors=True)  # the temporary Edge profile
