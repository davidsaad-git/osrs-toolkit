# Builds ../OSRS Toolkit.html from the four tool pages in this folder.
# Each tool's CSS is prefix-scoped (#t-<key>) and its JS wrapped in an IIFE,
# so the merged single-file app can't have style or variable collisions.
# Run:  python build_toolkit.py
import io, os, re, sys, glob, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "OSRS Toolkit.html")

TOOLS = [
    # (key, source file, icon, tab label, dimmed nav tab)
    ("ledger",  "Ledger.html",       "⚔️", "Ledger",      False),
    ("oracle",  "Drop Oracle.html",  "🎲", "Drop Oracle", True),
    ("upgrade", "Upgrade Path.html", "🗡️", "Upgrades",    True),
    ("toa",     "ToA Notes.html",    "🏺", "ToA Notes",   True),
]

def prefix_css(css, pfx):
    """Prefix every selector with pfx; drop :root/body/* rules (shared block covers them)."""
    res, i, n = [], 0, len(css)
    while i < n:
        while i < n and css[i] in " \t\r\n":
            res.append(css[i]); i += 1
        if i >= n: break
        if css.startswith("@media", i):
            j = css.index("{", i); depth, k = 1, j + 1
            while depth:
                if css[k] == "{": depth += 1
                elif css[k] == "}": depth -= 1
                k += 1
            res.append(css[i:j+1]); res.append(prefix_css(css[j+1:k-1], pfx)); res.append("}")
            i = k
            continue
        j = css.find("{", i)
        if j == -1: break
        k = css.index("}", j)
        sel, body = css[i:j].strip(), css[j+1:k]
        if sel not in (":root", "body", "*"):
            sel = ",".join(f"{pfx} {s.strip()}" for s in sel.split(","))
            res.append(sel + "{" + body + "}\n")
        i = k + 1
    return "".join(res)

def extract(path):
    t = io.open(path, encoding="utf-8").read()
    style = re.search(r"<style>(.*?)</style>", t, re.S).group(1)
    script = re.search(r"<script>(.*?)</script>", t, re.S)
    body = t[t.index("</style>") + len("</style>"):]
    if script:
        body = body[: body.index("<script>")]
    js = script.group(1) if script else ""
    if "__SNAPSHOTS__" in js:
        snaps = io.open(os.path.join(HERE, "snapshots.json"), encoding="utf-8").read()
        js = js.replace("__SNAPSHOTS__", snaps)
    if "__CLOGCATS__" in js:
        cats = io.open(os.path.join(HERE, "clog_categories.json"), encoding="utf-8").read()
        js = js.replace("__CLOGCATS__", cats)
    if "__QUESTS__" in js:
        qm = io.open(os.path.join(HERE, "quests_meta.json"), encoding="utf-8").read()
        js = js.replace("__QUESTS__", qm)
    return style, js, body.strip()

SHELL_CSS = """
:root{
  --ground:#16120d; --panel:#211b13; --panel2:#2a2318; --panel3:#332a1c;
  --border:#4d3d24; --border-soft:#3a2f1d;
  --ink:#e9dcbe; --muted:#a08c66; --faint:#6f6047;
  --gold:#f5c235; --green:#9ad24b; --red:#e0674f; --blue:#7fb8d9;
  --c-davo:#f5c235; --c-dog:#9ad24b; --c-arch:#e08e45;
  --display:'Cinzel',Georgia,serif;
  --sans:'IBM Plex Sans',system-ui,sans-serif;
  --mono:'IBM Plex Mono',Consolas,monospace;
}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{background:var(--ground);color:var(--ink);font-family:var(--sans);margin:0;
  font-size:14px;line-height:1.5}
nav{position:sticky;top:0;z-index:10;background:var(--ground);
  border-bottom:2px solid var(--border);display:flex;gap:2px;
  padding:10px 16px 0;overflow-x:auto}
nav .brand{font-family:var(--display);font-weight:700;font-size:15px;color:var(--gold);
  letter-spacing:.03em;padding:8px 14px 10px 0;white-space:nowrap}
nav button{font:inherit;font-size:13.5px;font-weight:500;color:var(--muted);
  background:none;border:none;border-bottom:3px solid transparent;
  padding:8px 14px 10px;cursor:pointer;white-space:nowrap}
nav button:hover{color:var(--ink)}
nav button.on{color:var(--gold);border-bottom-color:var(--gold)}
nav button:focus-visible{outline:2px solid var(--gold);outline-offset:-2px}
nav button.dim{opacity:.35;filter:grayscale(1);cursor:not-allowed}
nav button.dim:hover{color:var(--muted)}
"""

# --- Installable-app (PWA) wiring -------------------------------------------
# The page is added to an iPhone home screen via Safari > Share > Add to Home
# Screen. The apple-* meta tags are what make it launch standalone (no Safari
# UI); the manifest covers Android and desktop.
PWA_HEAD = """<link rel="stylesheet" href="assets/fonts.css">
<link rel="manifest" href="manifest.webmanifest">
<meta name="theme-color" content="#16120d">
<meta name="color-scheme" content="dark">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="Quit Smoking">
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="192x192" href="assets/icon-192.png">"""

# Best-effort: there is no service worker on file:// or insecure origins, and
# the page has to keep working when opened straight off disk.
PWA_SCRIPT = """<script>
if("serviceWorker" in navigator && location.protocol.indexOf("http")===0){
  addEventListener("load",function(){
    navigator.serviceWorker.register("sw.js")["catch"](function(){});
  });
}
</script>"""

SW_TEMPLATE = """// Generated by src/build_toolkit.py - do not edit by hand.
// VERSION is a hash of the built page, so each data refresh publishes a new
// cache and clients stop serving stale numbers.
var CACHE = "qs-toolkit-__VERSION__";
var PRECACHE = __PRECACHE__;

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    // One bad asset must not fail the whole install.
    return Promise.all(PRECACHE.map(function (u) {
      return c.add(new Request(u, { cache: "reload" }))["catch"](function () {});
    }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.map(function (k) {
      return k === CACHE ? null : caches.delete(k);
    }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  if (new URL(req.url).origin !== location.origin) return;

  // Navigations: network first, so a refresh lands as soon as there is
  // signal; fall back to cache so the app still opens with no connection.
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then(function (res) {
      var copy = res.clone();
      caches.open(CACHE).then(function (c) { c.put("./", copy); });
      return res;
    })["catch"](function () {
      return caches.match("./").then(function (r) {
        return r || caches.match("index.html");
      });
    }));
    return;
  }

  // Fonts, icons, manifest: immutable within a version, so cache first.
  e.respondWith(caches.match(req).then(function (hit) {
    return hit || fetch(req).then(function (res) {
      if (res && res.ok && res.type === "basic") {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(req, copy); });
      }
      return res;
    });
  }));
});
"""

def write_sw(root, doc):
    """Emit sw.js with a precache list scanned from disk and a content hash."""
    version = hashlib.sha256(doc.encode("utf-8")).hexdigest()[:12]
    files = ["./", "manifest.webmanifest", "assets/fonts.css"]
    for pat in ("assets/fonts/*.woff2", "assets/*.png"):
        files += sorted(
            os.path.relpath(f, root).replace(os.sep, "/")
            for f in glob.glob(os.path.join(root, pat))
        )
    body = SW_TEMPLATE.replace("__VERSION__", version)
    body = body.replace("__PRECACHE__", "[\n  " + ",\n  ".join('"%s"' % f for f in files) + "\n]")
    io.open(os.path.join(root, "sw.js"), "w", encoding="utf-8").write(body)
    return version, len(files)


def main():
    parts_css, parts_html, parts_js, tabs = [], [], [], []
    for key, fname, ico, label, dim in TOOLS:
        style, script, body = extract(os.path.join(HERE, fname))
        parts_css.append(f"/* ---- {key} ---- */\n" + prefix_css(style, f"#t-{key}"))
        parts_html.append(f'<div id="t-{key}" class="tool" hidden>\n{body}\n</div>')
        if script:
            parts_js.append(f"/* ---- {key} ---- */\n(function(){{\n{script}\n}})();")
        tabs.append(f'<button data-t="{key}"{" class=\"dim\" disabled" if dim else ""}>{ico} {label}</button>')

    dis_json = "{" + ",".join(f'"{k}":1' for k, _, _, _, d in TOOLS if d) + "}"
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quit Smoking — Group Highscores</title>
{PWA_HEAD}
<style>
{SHELL_CSS}
{"".join(parts_css)}
</style>
</head>
<body>
<nav><span class="brand">Quit Smoking</span>{"".join(tabs)}</nav>
{"".join(parts_html)}
<script>
(function(){{
  var tabs=document.querySelectorAll("nav button"),cur="ledger";
  var dis={dis_json};
  try{{cur=localStorage.getItem("toolkit-tab")||cur}}catch(e){{}}
  if(dis[cur])cur="ledger";
  function show(k){{
    cur=k;
    tabs.forEach(function(b){{b.classList.toggle("on",b.dataset.t===k)}});
    document.querySelectorAll(".tool").forEach(function(d){{d.hidden=d.id!=="t-"+k}});
    try{{localStorage.setItem("toolkit-tab",k)}}catch(e){{}}
  }}
  tabs.forEach(function(b){{b.onclick=function(){{show(b.dataset.t)}}}});
  show(document.getElementById("t-"+cur)?cur:"ledger");
  // Sticky table headers park just below the nav bar.
  var nav=document.querySelector("nav");
  function setSticky(){{document.documentElement.style.setProperty("--stickytop",nav.offsetHeight+"px")}}
  setSticky();window.addEventListener("resize",setSticky);
}})();
</script>
<script>
{"".join(parts_js)}
</script>
{PWA_SCRIPT}
</body>
</html>
"""
    io.open(OUT, "w", encoding="utf-8").write(doc)
    # Same document as index.html so GitHub Pages serves it at the bare repo URL.
    io.open(os.path.join(HERE, "..", "index.html"), "w", encoding="utf-8").write(doc)
    root = os.path.normpath(os.path.join(HERE, ".."))
    ver, n = write_sw(root, doc)
    print("built", os.path.abspath(OUT), f"({len(doc):,} bytes) + index.html")
    print(f"built sw.js (cache qs-toolkit-{ver}, {n} precached files)")

if __name__ == "__main__":
    main()
