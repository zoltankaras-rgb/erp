import pathlib

roots = [
    pathlib.Path(r"C:\Users\zolko\Desktop\NOVEERP\projekt\templates"),
    pathlib.Path(r"C:\Users\zolko\Desktop\NOVEERP\projekt\static\js"),
    pathlib.Path(r"C:\Users\zolko\Desktop\NOVEERP\projekt\static\css"),
]
exts = {".html", ".js", ".css"}

for root in roots:
    for p in root.rglob("*"):
        if p.suffix.lower() in exts and p.is_file():
            raw = p.read_bytes()
            try:
                raw.decode("utf-8")
                continue  # už je OK
            except UnicodeDecodeError:
                pass
            # skús cp1250, ak nie, skús latin-1
            try:
                text = raw.decode("cp1250")
            except UnicodeDecodeError:
                text = raw.decode("latin-1", errors="replace")
            # záloha
            p.with_suffix(p.suffix + ".bak").write_bytes(raw)
            # ulož v UTF-8
            p.write_text(text, encoding="utf-8")
            print(f"Converted -> {p}")
