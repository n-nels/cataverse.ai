import subprocess, sys
from ollama import Client
c = Client(host="http://localhost:11434")
model = sys.argv[1]
for ctx in [8192, 16384, 32768, 65536]:
    try:
        c.chat(model=model, messages=[{"role":"user","content":"hi"}],
               options={"num_ctx": ctx})
    except Exception as e:
        print(f"{ctx:>7}  ERROR {str(e)[:80]}"); continue
    ps = subprocess.run(["ollama","ps"], capture_output=True, text=True).stdout
    line = [l for l in ps.splitlines() if l.startswith(model.split(":")[0])]
    print(f"{ctx:>7}  {line[0] if line else '(not resident)'}")
    subprocess.run(["ollama","stop",model], capture_output=True)
