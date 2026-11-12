# -*- coding: utf-8 -*-
"""
ASSISTENTE DE E-MAILS DE LOGÍSTICA (IA) — triagem automática da caixa de entrada.

Para cada e-mail (.txt ou .eml) de uma pasta:
  1) o Claude lê o texto e devolve dados ESTRUTURADOS: categoria, urgência, O.C.s,
     data/hora/senha de agenda, ação sugerida e um RASCUNHO de resposta;
  2) regras em Python cruzam isso com a base de cargas do sistema (CSV) e apontam
     divergências (agenda diferente, O.C. inexistente, carga sem transporte perto da data);
  3) gera um painel HTML ordenado por urgência + um CSV.

NADA é enviado: o rascunho é só para o analista revisar e mandar.

Uso:
    set ANTHROPIC_API_KEY=sua_chave      (nunca coloque a chave no código)
    python triagem.py exemplos/emails exemplos/base_cargas.csv
"""
import argparse
import csv
import email
import html
import os
import sys
from datetime import date
from email import policy
from pathlib import Path

import anthropic

from modelos import Triagem
from regras import conferir, ler_base

MODELO = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
ESFORCO = os.environ.get("CLAUDE_EFFORT", "medium")   # low | medium | high

SYSTEM = """Você é assistente de um analista de transportes de um centro de distribuição.
Leia UM e-mail e preencha o formato pedido.

Regras:
- Use SOMENTE o que está escrito no e-mail. Nunca invente data, hora, senha ou número de O.C.
  Se não estiver no texto, use null e coloque o item em "informacao_faltando".
- Datas no formato dd/mm/aaaa; horas HH:MM. Se o ano não aparecer, use o ano da data do e-mail.
- O.C. = ordem de carga (números de 5 a 6 dígitos). Pedido/NF não são O.C.
- Rascunho de resposta: curto, neutro, educado, em português, sem acusar ninguém.
  Não cite o nome da transportadora no rascunho; escreva "a transportadora".
  Não prometa data que não está no e-mail. Assine apenas "Equipe de Transportes".
"""


def ler_email(caminho: Path) -> str:
    """Texto do e-mail: .eml (cabeçalhos + corpo) ou .txt como está."""
    if caminho.suffix.lower() != ".eml":
        return caminho.read_text(encoding="utf-8", errors="replace")
    msg = email.message_from_bytes(caminho.read_bytes(), policy=policy.default)
    corpo = msg.get_body(preferencelist=("plain", "html"))
    texto = corpo.get_content() if corpo else ""
    return f"De: {msg['from']}\nData: {msg['date']}\nAssunto: {msg['subject']}\n\n{texto}"


def triar(client: anthropic.Anthropic, texto: str) -> Triagem:
    """Uma chamada ao Claude com saída estruturada (validada pelo Pydantic)."""
    resp = client.beta.messages.parse(
        model=MODELO,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",              # se o modelo recusar, a API tenta outro modelo sozinha
        output_config={"effort": ESFORCO},
        system=SYSTEM,
        messages=[{"role": "user", "content": f"<email>\n{texto}\n</email>"}],
        output_format=Triagem,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("o modelo recusou este e-mail")
    if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
        raise RuntimeError(f"resposta incompleta (stop_reason={resp.stop_reason})")
    return resp.parsed_output


ORDEM = {"alta": 0, "media": 1, "baixa": 2}


def gerar_html(itens: list[dict], destino: Path) -> None:
    def esc(x):
        return html.escape(str(x or ""))
    cards = []
    for it in itens:
        t: Triagem | None = it["triagem"]
        if t is None:
            cards.append(f'<section class="card erro"><h2>{esc(it["arquivo"])}</h2><p>Erro: {esc(it["erro"])}</p></section>')
            continue
        cargas = "".join(
            f"<li><b>O.C. {esc(c.oc)}</b> {esc(c.cliente)} · agenda {esc(c.data_agenda) or '—'} {esc(c.hora_agenda)}"
            f"{' · senha ' + esc(c.senha_agenda) if c.senha_agenda else ''}</li>" for c in t.cargas) or "<li>—</li>"
        alertas = "".join(f"<li>{esc(a)}</li>" for a in it["alertas"])
        falta = ", ".join(t.informacao_faltando)
        cards.append(f"""<section class="card {t.urgencia}">
  <header><span class="tag">{esc(t.urgencia)}</span><span class="cat">{esc(t.categoria)}</span>
  <small>{esc(it['arquivo'])}</small></header>
  <p class="resumo">{esc(t.resumo)}</p>
  <ul>{cargas}</ul>
  {'<div class="alerta"><b>Conferência com o sistema</b><ul>' + alertas + '</ul></div>' if alertas else ''}
  <p><b>Ação:</b> {esc(t.acao_sugerida)}</p>
  {f'<p><b>Falta:</b> {esc(falta)}</p>' if falta else ''}
  <details><summary>Rascunho de resposta (não enviado)</summary><pre>{esc(t.rascunho_resposta)}</pre></details>
</section>""")
    destino.write_text(f"""<!doctype html><html lang="pt-br"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Triagem de e-mails</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--tx:#1d2330;--mu:#5b6475;--al:#c0392b;--md:#b7791f;--bx:#2f855a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151b;--card:#1b2029;--tx:#e8ebf0;--mu:#9aa3b2}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--tx);font:15px/1.45 system-ui,Segoe UI,sans-serif}}
main{{max-width:900px;margin:auto}} h1{{font-size:22px}}
.card{{background:var(--card);border-radius:10px;padding:14px 16px;margin:12px 0;border-left:6px solid var(--mu)}}
.card.alta{{border-color:var(--al)}} .card.media{{border-color:var(--md)}} .card.baixa{{border-color:var(--bx)}}
header{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}} small{{color:var(--mu);margin-left:auto}}
.tag{{text-transform:uppercase;font-weight:700;font-size:12px}} .cat{{background:#8881;padding:2px 8px;border-radius:99px;font-size:12px}}
.resumo{{font-weight:600}} .alerta{{background:#c0392b18;border-radius:8px;padding:6px 12px}}
pre{{white-space:pre-wrap;background:#8881;padding:10px;border-radius:8px}}
</style><main><h1>Triagem de e-mails — {date.today():%d/%m/%Y}</h1>
<p>{len(itens)} e-mail(s). Ordenado por urgência. Rascunhos NÃO foram enviados.</p>
{''.join(cards)}</main></html>""", encoding="utf-8")


def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser(description="Triagem de e-mails de logística com Claude")
    ap.add_argument("pasta_emails", type=Path)
    ap.add_argument("base_cargas", type=Path)
    ap.add_argument("--saida", type=Path, default=Path("saida"))
    ap.add_argument("--hoje", help="data de referência dd/mm/aaaa (padrão: hoje)")
    a = ap.parse_args(argv)

    hoje = date.today() if not a.hoje else date(*map(int, reversed(a.hoje.split("/"))))
    base = ler_base(a.base_cargas)
    client = client or anthropic.Anthropic()   # lê ANTHROPIC_API_KEY do ambiente
    arquivos = sorted(p for p in a.pasta_emails.iterdir() if p.suffix.lower() in (".txt", ".eml"))
    itens = []
    for arq in arquivos:
        print(f"• {arq.name} ...", end=" ", flush=True)
        try:
            t = triar(client, ler_email(arq))
            itens.append({"arquivo": arq.name, "triagem": t, "alertas": conferir(t, base, hoje), "erro": ""})
            print(t.categoria, "/", t.urgencia)
        except anthropic.AuthenticationError:
            print("\nChave da API inválida ou ausente (ANTHROPIC_API_KEY).")
            return 2
        except anthropic.RateLimitError:
            itens.append({"arquivo": arq.name, "triagem": None, "alertas": [], "erro": "limite de uso — rode de novo depois"})
            print("limite de uso")
        except (anthropic.APIStatusError, anthropic.APIConnectionError, RuntimeError) as e:
            itens.append({"arquivo": arq.name, "triagem": None, "alertas": [], "erro": str(e)})
            print("erro:", e)

    itens.sort(key=lambda i: (i["triagem"] is None, ORDEM.get(i["triagem"].urgencia, 9) if i["triagem"] else 9))
    a.saida.mkdir(exist_ok=True)
    gerar_html(itens, a.saida / "triagem.html")
    with open(a.saida / "triagem.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["arquivo", "categoria", "urgencia", "ocs", "resumo", "acao", "alertas"])
        for it in itens:
            t = it["triagem"]
            w.writerow([it["arquivo"], t.categoria if t else "ERRO", t.urgencia if t else "",
                        ", ".join(c.oc for c in t.cargas) if t else "", t.resumo if t else it["erro"],
                        t.acao_sugerida if t else "", " | ".join(it["alertas"])])
    print(f"\nPronto: {a.saida / 'triagem.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
