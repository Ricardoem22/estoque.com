# backup.py
import shutil
from datetime import datetime
from pathlib import Path

BACKUP_DIR = Path("backups")


def criar_backup(db_path="estoque.db"):
    """Cria uma cópia do banco antes de operações críticas."""
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = BACKUP_DIR / f"estoque_backup_{timestamp}.db"
    shutil.copy(db_path, destino)
    return destino


def limpar_backups_antigos(dias=30):
    """Remove backups com mais de N dias."""
    import time
    agora = time.time()
    for arquivo in BACKUP_DIR.glob("*.db"):
        idade_dias = (agora - arquivo.stat().st_mtime) / 86400
        if idade_dias > dias:
            arquivo.unlink()
