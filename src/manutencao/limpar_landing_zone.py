"""
Limpeza da Landing Zone — remove partições data=AAAA-MM-DD/ mais antigas
que a retenção definida (ADR-009), por sistema.

Modo dry_run (padrão True) apenas lista o que seria removido, sem remover
de fato — validação antes de executar algo irreversível.

data_referencia é parametrizável para permitir testar sem esperar 30 dias
reais passarem (ADR-009: usar uma data simulada no futuro).
"""

from datetime import date, timedelta


def limpar_landing_zone(
    spark,
    dbutils,
    sistema: str,
    dias_retencao: int = 30,
    data_referencia: date = None,
    dry_run: bool = True,
    catalog: str = "poc_pulse_observability",
    volume_landing: str = "raw",
) -> dict:
    """Remove (ou lista, em dry_run) partições data=AAAA-MM-DD/ vencidas na Landing Zone de um sistema."""
    if data_referencia is None:
        data_referencia = date.today()

    data_corte = data_referencia - timedelta(days=dias_retencao)

    caminho_sistema = f"/Volumes/{catalog}/landing/{volume_landing}/{sistema}"
    entradas = dbutils.fs.ls(caminho_sistema)

    particoes_avaliadas = []
    particoes_a_remover = []

    for entrada in entradas:
        nome = entrada.name.rstrip("/")
        if not nome.startswith("data="):
            continue  # ignora _seed, _autoloader_schema etc. — não são partição de data

        particoes_avaliadas.append(nome)
        data_str = nome.replace("data=", "")
        try:
            data_particao = date.fromisoformat(data_str)
        except ValueError:
            continue  # nome inesperado, não tenta interpretar

        if data_particao < data_corte:
            particoes_a_remover.append(nome)

    particoes_removidas = []
    if not dry_run:
        for particao in particoes_a_remover:
            dbutils.fs.rm(f"{caminho_sistema}/{particao}", recurse=True)
            particoes_removidas.append(particao)

    return {
        "sistema": sistema,
        "dry_run": dry_run,
        "data_corte": str(data_corte),
        "particoes_avaliadas": len(particoes_avaliadas),
        "particoes_a_remover": particoes_a_remover,
        "particoes_removidas": particoes_removidas,
    }