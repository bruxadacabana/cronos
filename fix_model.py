"""
Roda na pasta raiz do cronos:
  python fix_model.py
Grava o modelo correto nas settings e confirma.
"""
import sys
sys.path.insert(0, "src")
from core.database import get_setting, set_setting

print("Modelos disponíveis detectados: kimi-k2.5:cloud, qwen3.5:397b-cloud")
print(f"Modelo atual salvo: {repr(get_setting('ollama_model', ''))}")

set_setting("ollama_model", "kimi-k2.5:cloud")

print(f"Modelo salvo agora: {repr(get_setting('ollama_model', ''))}")
print("Pronto. Reinicie o Cronos.")
