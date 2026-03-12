"""
Cronos - Sistema de Logging Centralizado
Configura dois destinos de log:

  data/logs/cronos.log      — log geral da aplicação (INFO+)
  data/logs/analysis.log    — log detalhado de análises de IA (DEBUG+)

Rotação automática: máximo 2 MB por arquivo, 5 backups mantidos.
Formato legível com separadores visuais para erros.
"""
import logging
import logging.handlers
import sys
import traceback
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR  = BASE_DIR / "data" / "logs"


class _AnalysisFilter(logging.Filter):
    """Deixa passar apenas logs dos módulos de IA/análise."""
    MODULES = {"cronos.analyzer", "cronos.ai", "cronos.translator"}

    def filter(self, record):
        return any(record.name.startswith(m) for m in self.MODULES)


class _ErrorSeparatorFormatter(logging.Formatter):
    """Adiciona separador visual antes de cada ERROR/CRITICAL."""
    _SEP = "─" * 60

    def format(self, record):
        msg = super().format(record)
        if record.levelno >= logging.ERROR:
            return f"\n{self._SEP}\n{msg}\n{self._SEP}"
        return msg


def setup_logging(debug: bool = False) -> None:
    """
    Configura o sistema de logging completo.
    Deve ser chamado UMA VEZ em cronos.py antes de qualquer import de módulo Cronos.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)   # captura tudo; handlers filtram

    # ── Formato base ────────────────────────────────────────────────────────
    fmt_normal = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    fmt_error = _ErrorSeparatorFormatter(
        "%(asctime)s [%(levelname)-8s] %(name)s\n"
        "%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # ── Handler 1: cronos.log — log geral (INFO+) ──────────────────────────
    general_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "cronos.log",
        maxBytes=2 * 1024 * 1024,   # 2 MB
        backupCount=5,
        encoding="utf-8"
    )
    general_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    general_handler.setFormatter(fmt_normal)
    # Filtra apenas logs do Cronos (exclui bibliotecas externas barulhentas)
    general_handler.addFilter(logging.Filter("cronos"))
    root.addHandler(general_handler)

    # ── Handler 2: analysis.log — log de IA (DEBUG+) ──────────────────────
    analysis_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "analysis.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    analysis_handler.setLevel(logging.DEBUG)
    analysis_handler.setFormatter(_ErrorSeparatorFormatter(
        "%(asctime)s [%(levelname)-8s] %(name)s\n%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    analysis_handler.addFilter(_AnalysisFilter())
    root.addHandler(analysis_handler)

    # ── Handler 3: stderr — apenas WARNING+ no terminal ───────────────────
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter(
        "[%(levelname)s] %(name)s: %(message)s"
    ))
    root.addHandler(console_handler)

    # ── Silencia libs externas barulhentas ─────────────────────────────────
    for noisy in ("httpx", "httpcore", "urllib3", "feedparser",
                  "charset_normalizer", "PIL", "PyQt6"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("cronos").info(
        f"=== Cronos iniciado — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==="
    )


def log_analysis_start(article_id: int, title: str, mode: str) -> None:
    """Log padronizado de início de análise."""
    logger = logging.getLogger("cronos.analyzer")
    logger.info(
        f"[{mode.upper()}] ► Iniciando análise\n"
        f"  ID    : {article_id}\n"
        f"  Título: {title[:100]}"
    )


def log_analysis_result(article_id: int, result: dict, elapsed: float, mode: str) -> None:
    """Log padronizado de resultado de análise."""
    logger = logging.getLogger("cronos.analyzer")
    summary_preview = (result.get("ai_summary") or "")[:80].replace("\n", " ")
    logger.info(
        f"[{mode.upper()}] ✓ Concluído em {elapsed:.1f}s\n"
        f"  ID         : {article_id}\n"
        f"  Categoria  : {result.get('ai_category', '—')}\n"
        f"  Tom        : {result.get('emotional_tone', '—')}\n"
        f"  Clickbait  : {result.get('clickbait_score', '—')}\n"
        f"  Resumo     : {summary_preview}{'…' if len(summary_preview)==80 else ''}"
    )


def log_analysis_error(article_id: int, title: str, error: Exception,
                       chunk: int = None, mode: str = "batch") -> None:
    """Log padronizado de erro de análise com traceback completo."""
    logger = logging.getLogger("cronos.analyzer")
    chunk_info = f" (chunk {chunk})" if chunk is not None else ""
    logger.error(
        f"[{mode.upper()}] ✗ Falha na análise{chunk_info}\n"
        f"  ID    : {article_id}\n"
        f"  Título: {title[:100]}\n"
        f"  Erro  : {type(error).__name__}: {error}",
        exc_info=True
    )


def log_ollama_call(prompt_len: int, max_tokens: int, timeout: int,
                    success: bool, elapsed: float, error: str = None) -> None:
    """Log de cada chamada ao Ollama."""
    logger = logging.getLogger("cronos.ai")
    if success:
        logger.debug(
            f"Ollama OK — prompt:{prompt_len}c max_tokens:{max_tokens} "
            f"timeout:{timeout}s elapsed:{elapsed:.2f}s"
        )
    else:
        logger.error(
            f"Ollama FALHOU — prompt:{prompt_len}c max_tokens:{max_tokens} "
            f"timeout:{timeout}s elapsed:{elapsed:.2f}s\n"
            f"  Erro: {error}"
        )
