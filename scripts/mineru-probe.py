import subprocess, tempfile
from pathlib import Path

data = open(r'D:\paper\dsh\platform-langgraph\backend\data\tmp\documents\fc69d9e2-78f2-4b53-aba6-bc0a26dbdf4a\original.pdf','rb').read()
with tempfile.TemporaryDirectory() as tmp:
    pdf_path = Path(tmp)/'in.pdf'
    pdf_path.write_bytes(data)
    out = Path(tmp)/'out'
    out.mkdir()
    proc = subprocess.Popen(
        ['D:/software/anaconda/envs/mineru/Scripts/mineru.exe','-p',str(pdf_path),'-o',str(out)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace'
    )
    progress_lines = []
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        if any(k in line.lower() for k in ['%', 'progress', 'page', '页', 'processing', 'done', 'predict', 'layout']):
            progress_lines.append(line.strip()[:100])
    proc.kill()
    print('stdout matching lines:', len(progress_lines))
    for l in progress_lines[:15]:
        print('  ', l)
