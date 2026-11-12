# -*- coding: utf-8 -*-
"""Conferência DETERMINÍSTICA (sem IA): cruza o que o Claude extraiu do e-mail
com a base de cargas do sistema e aponta divergências.

A IA lê o texto livre; as regras de negócio ficam em Python puro, testáveis.
"""
import csv
from datetime import date, datetime
from pathlib import Path

from modelos import Triagem


def ler_base(caminho: Path) -> dict[str, dict]:
    """CSV ';' com colunas: oc;cliente;cidade_uf;agenda_sistema;status;transportadora"""
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        return {linha["oc"].strip(): linha for linha in csv.DictReader(f, delimiter=";")}


def _data(txt: str | None) -> date | None:
    if not txt:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(txt.strip(), fmt).date()
        except ValueError:
            pass
    return None


def dias_uteis_ate(hoje: date, alvo: date) -> int:
    """Dias úteis (seg–sex) entre hoje (exclusive) e o alvo (inclusive). Negativo se já passou."""
    if alvo <= hoje:
        return -(hoje - alvo).days
    n, d = 0, hoje
    while d < alvo:
        d = date.fromordinal(d.toordinal() + 1)
        if d.weekday() < 5:
            n += 1
    return n


def conferir(t: Triagem, base: dict[str, dict], hoje: date) -> list[str]:
    """Lista de alertas para o analista. Vazia = nada estranho."""
    alertas = []
    if not t.cargas and t.categoria in ("reagendamento", "agenda_confirmada", "cobranca_status"):
        alertas.append("E-mail não cita nenhuma O.C. — pedir o número antes de agir.")
    for c in t.cargas:
        reg = base.get(c.oc)
        if reg is None:
            alertas.append(f"O.C. {c.oc} não encontrada na base do sistema.")
            continue
        ag_email = _data(c.data_agenda)
        ag_sist = _data(reg.get("agenda_sistema"))
        if ag_email and ag_sist and ag_email != ag_sist:
            alertas.append(f"O.C. {c.oc}: e-mail diz {c.data_agenda}, sistema está {reg['agenda_sistema']} — atualizar.")
        if ag_email and not ag_sist:
            alertas.append(f"O.C. {c.oc}: agenda {c.data_agenda} ainda não lançada no sistema.")
        status = (reg.get("status") or "").upper()
        alvo = ag_email or ag_sist
        if alvo and "CONTRATANDO" in status:
            du = dias_uteis_ate(hoje, alvo)
            if du <= 2:
                alertas.append(f"O.C. {c.oc}: agenda em {du} dia(s) útil(eis) e transporte ainda NÃO contratado.")
        if t.categoria == "reagendamento" and "EXPEDIDO" in status:
            alertas.append(f"O.C. {c.oc} já foi expedida — reagenda precisa ser tratada com quem está transportando.")
    return alertas
