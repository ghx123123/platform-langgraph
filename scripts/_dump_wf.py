import json

path = (r"C:\Users\84652\.claude\projects\D--paper-dsh\225b2dad-6310-4fcc-a5b7-64ba53959877"
        r"\subagents\workflows\wf_46ad7efb-810\journal.jsonl")
out = r"D:\paper\dsh\platform-langgraph\.runtime\wf_testplan.json"

res = []
for line in open(path, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    d = json.loads(line)
    if d.get("type") == "result":
        res.append(d)

print("results:", len(res))
for i, d in enumerate(res):
    print(i, list(d.keys()), str(d.get("label"))[:40], len(json.dumps(d, ensure_ascii=False)))

with open(out, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print("written", out)
