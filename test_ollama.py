"""
Roda no diretório do cronos:
  python test_ollama.py
Imprime o body exato do erro 400 do Ollama.
"""
import sys, json
sys.path.insert(0, "src")

try:
    from core.database import get_setting
    url   = get_setting("ollama_url",   "http://localhost:11434")
    model = get_setting("ollama_model", "")
except Exception as e:
    print(f"[AVISO] Não consegui ler settings: {e}")
    url   = "http://localhost:11434"
    model = input("Nome do modelo (ex: kimi:latest): ").strip()

print(f"\n=== Configuração ===")
print(f"  URL  : {url}")
print(f"  Model: {repr(model)}")

import httpx

# Teste 1 — payload mínimo /api/chat
print("\n=== Teste 1: /api/chat payload mínimo ===")
p1 = {"model": model, "stream": False, "messages": [{"role": "user", "content": "responda apenas: ok"}]}
try:
    r = httpx.post(f"{url}/api/chat", json=p1, timeout=10)
    print(f"  Status: {r.status_code}")
    try: print(f"  Body  : {r.json()}")
    except: print(f"  Body  : {r.text[:300]}")
except Exception as e:
    print(f"  Erro  : {e}")

# Teste 2 — /api/generate
print("\n=== Teste 2: /api/generate ===")
p2 = {"model": model, "stream": False, "prompt": "responda apenas: ok"}
try:
    r = httpx.post(f"{url}/api/generate", json=p2, timeout=10)
    print(f"  Status: {r.status_code}")
    try: print(f"  Body  : {r.json()}")
    except: print(f"  Body  : {r.text[:300]}")
except Exception as e:
    print(f"  Erro  : {e}")

# Teste 3 — /api/tags (listar modelos)
print("\n=== Teste 3: /api/tags (modelos disponíveis) ===")
try:
    r = httpx.get(f"{url}/api/tags", timeout=5)
    print(f"  Status: {r.status_code}")
    data = r.json()
    models = [m["name"] for m in data.get("models", [])]
    print(f"  Modelos: {models}")
except Exception as e:
    print(f"  Erro  : {e}")

print("\n=== Fim ===")
