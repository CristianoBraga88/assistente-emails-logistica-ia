# Assistente de E-mails de Logística (IA)

> ⚠️ **Dados fictícios.** E-mails, clientes e cargas de `exemplos/` são inventados.

Triagem automática da caixa de entrada de um analista de transportes usando a **API do Claude (Anthropic)**.
Cada e-mail vira um registro estruturado e é conferido contra a base de cargas do sistema.

## Problema
O analista recebe dezenas de e-mails por dia com pedidos de reagendamento, agendas confirmadas, cobranças
de previsão e problemas de entrega, em texto livre. Ler, achar a O.C., comparar com o sistema e responder
é manual e é onde erros acontecem (agenda do e-mail diferente da do sistema, carga sem transporte perto da data).

## Como funciona
```
e-mails (.txt/.eml) ──► Claude (structured outputs / Pydantic) ──► Triagem validada
                                                                     │
base de cargas (CSV) ──► regras.py (Python puro, testado) ───────────┤
                                                                     ▼
                                     painel HTML por urgência + CSV + rascunhos de resposta
```
1. **IA para o que é texto livre:** categoria, urgência, O.C.s, data/hora/senha, ação sugerida, o que está faltando e um rascunho de resposta.
2. **Código para o que é regra:** divergência de agenda, O.C. inexistente, agenda lançada ou não, carga "contratando" a ≤2 dias úteis, reagenda de carga já expedida.
3. **Humano no controle:** nada é enviado. O rascunho fica para revisão.

## Decisões de projeto
- **Saída estruturada** (`client.beta.messages.parse` + `output_format=Triagem`): a resposta já chega validada, sem parse de texto.
- **Anti-alucinação no prompt:** nunca inventar data/hora/senha; se não está no e-mail, vira `null` + item em `informacao_faltando`.
- **Fallback de recusa** no servidor (`fallbacks="default"`) e tratamento de `stop_reason` (`refusal`, `max_tokens`).
- **Erros tratados por tipo** (`AuthenticationError`, `RateLimitError`, `APIStatusError`, `APIConnectionError`): um e-mail com erro não derruba a triagem dos outros.
- **Testes offline**: a requisição HTTP é interceptada, então dá para testar o fluxo inteiro sem chave e sem custo.
- Modelo e esforço configuráveis por variável de ambiente (`CLAUDE_MODEL`, `CLAUDE_EFFORT`).

## Como rodar
```bash
pip install -r requirements.txt
set ANTHROPIC_API_KEY=sua_chave
python triagem.py exemplos/emails exemplos/base_cargas.csv --hoje 12/11/2026
# abre saida/triagem.html
```
Testes (sem chave):
```bash
python -m unittest discover -s tests -v
```

## Arquivos
| Arquivo | Função |
|---|---|
| `triagem.py` | lê os e-mails, chama o Claude, gera HTML e CSV |
| `modelos.py` | schema Pydantic da resposta (categoria, cargas, rascunho…) |
| `regras.py` | conferência determinística com a base de cargas |
| `tests/test_triagem.py` | 6 testes: regras + requisição + fluxo completo |
| `exemplos/` | 5 e-mails e uma base fictícios |

## Próximos passos
- Ler direto do Outlook / Microsoft Graph (somente leitura).
- Avaliação (eval) com e-mails rotulados para medir acerto por campo.

## Autor
Cristiano Braga — [github.com/CristianoBraga88](https://github.com/CristianoBraga88)
