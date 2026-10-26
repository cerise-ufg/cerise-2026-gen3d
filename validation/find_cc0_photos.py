"""Busca fotos reais de objetos com licenca livre (CC0 / dominio publico) no Wikimedia Commons e grava a lista
com URL, autor e licenca (para citar a fonte no relatorio)."""
import json
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "CERISE-UFG-research/1.0 (relatorio academico; contato via GitHub EduardoCaixeta)"}
QUERIES = ["teapot white background", "rubber duck", "sneaker shoe isolated", "toy car isolated", "coffee mug isolated",
           "teddy bear isolated", "action figure toy", "potted plant isolated", "wooden chair isolated", "alarm clock"]
OK_LIC = ("cc0", "public domain", "pd", "cc-zero")
if len(sys.argv) > 2:
    QUERIES = sys.argv[2:]


def q(params):
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


out = []
for s in QUERIES:
    d = q(dict(action="query", format="json", generator="search", gsrsearch=f"{s} filetype:bitmap", gsrnamespace=6,
               gsrlimit=25, prop="imageinfo", iiprop="url|size|extmetadata",
               iiextmetadatafilter="LicenseShortName|Artist|LicenseUrl", iiurlwidth=1024))
    for p in (d.get("query", {}).get("pages", {}) or {}).values():
        ii = p.get("imageinfo", [{}])[0]
        md = ii.get("extmetadata", {})
        lic = md.get("LicenseShortName", {}).get("value", "")
        if any(k in lic.lower() for k in OK_LIC) and ii.get("width", 0) >= 600:
            out.append(dict(query=s, title=p["title"], license=lic, artist=md.get("Artist", {}).get("value", "")[:120],
                            page=ii.get("descriptionurl"), thumb=ii.get("thumburl"), w=ii.get("width"),
                            h=ii.get("height")))
json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "cc0_candidates.json", "w"), indent=1, ensure_ascii=False)
for o in out:
    print(o["query"], "|", o["title"], "|", o["license"], "|", o["w"], "x", o["h"])
