import pathlib

root = pathlib.Path(r"C:\Users\zolko\Desktop\NOVEERP\projekt\templates")

for p in root.rglob("*.html"):
    raw = p.read_bytes()
    try:
        raw.decode("utf-8")
        print("OK (utf-8):", p.name)
        continue
    except UnicodeDecodeError:
        pass

    try:
        text = raw.decode("cp1250")
        p.with_suffix(p.suffix + ".bak").write_bytes(raw)  # záloha
        p.write_text(text, encoding="utf-8")               # uložiť ako utf-8
        print("Converted cp1250 -> utf-8:", p.name)
    except UnicodeDecodeError:
        print("SKIP (neviem dekódovať):", p.name)
