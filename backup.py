# backup.py
# Cópia de segurança automática: no primeiro acesso de cada dia o app copia o banco para a pasta de backups
# (BACKUP_DIR) e guarda os últimos 30 dias. A gerência também baixa uma cópia na hora em Funcionários.
import glob
import os
import sqlite3
import threading

import config

GUARDAR_DIAS = 30
_trava = threading.Lock()


def pasta():
    return os.environ.get("BACKUP_DIR") or os.path.join(os.path.dirname(os.path.abspath(config.DB_PATH)), "backups")


def copiar_banco(destino):
    """Cópia consistente mesmo com o app gravando (API de backup do SQLite)."""
    origem = sqlite3.connect(config.DB_PATH)
    copia = sqlite3.connect(destino)
    with copia:
        origem.backup(copia)
    copia.close()
    origem.close()


def backup_do_dia():
    """Faz o backup de hoje se ainda não existe. Devolve o caminho do arquivo ou None se já havia."""
    arquivo = os.path.join(pasta(), f"estoque-{config.hoje().isoformat()}.db")
    if os.path.exists(arquivo):
        return None
    with _trava:
        if os.path.exists(arquivo):
            return None
        os.makedirs(pasta(), exist_ok=True)
        temporario = arquivo + ".tmp"
        copiar_banco(temporario)
        os.replace(temporario, arquivo)
        for velho in sorted(glob.glob(os.path.join(pasta(), "estoque-*.db")))[:-GUARDAR_DIAS]:
            try:
                os.remove(velho)
            except OSError:
                pass
    return arquivo


def lista():
    """Backups guardados, do mais novo ao mais velho: [(nome, tamanho em KB)]."""
    return [(os.path.basename(a), max(1, os.path.getsize(a) // 1024))
            for a in sorted(glob.glob(os.path.join(pasta(), "estoque-*.db")), reverse=True)]


def tentar_backup_do_dia():
    # Backup nunca pode derrubar a tela: se der erro (disco cheio, permissão), o app segue
    try:
        backup_do_dia()
    except Exception:
        pass
