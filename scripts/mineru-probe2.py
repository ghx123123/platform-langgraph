import subprocess, tempfile, time
from pathlib import Path

data = open(r'D:\paper\dsh\platform-langgraph\backend\data\tmp\documents\fc69d9e2-78f2-4b53-aba6-bc0a26dbdf4a\original.pdf','rb').read()
with tempfile.TemporaryDirectory() as tmp:
    pdf_path = Path(tmp)/'in.pdf'
    pdf_path.write_bytes(data)
    out = Path(tmp)/'out'
    out.mkdir()
    proc = subprocess.Popen(
        ['D:/software/anaconda/envs/mineru/Scripts/mineru.exe','-p',str(pdf_path),'-o',str(out)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1
    )
    tail = []
    start = time.time()
    while proc.poll() is None:
        time.sleep(0.5)
        if time.time() - start > 25: break
    for line in proc.stdout:
        tail.append(line.rstrip()[:110])
    proc.kill()
    print('total output lines:', len(tail))
    for l in tail[-20:]: print('  ', l)
