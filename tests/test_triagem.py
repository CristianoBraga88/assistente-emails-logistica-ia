# -*- coding: utf-8 -*-
"""Testes SEM internet e SEM chave: a requisição HTTP é interceptada (httpx.MockTransport)."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import anthropic
import httpx2 as httpx   # cliente HTTP usado pelo SDK anthropic 1.x+

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import triagem                                   # noqa: E402
from modelos import Carga, Triagem               # noqa: E402
from regras import conferir, dias_uteis_ate, ler_base  # noqa: E402

BASE = ler_base(RAIZ / "exemplos" / "base_cargas.csv")
HOJE = date(2026, 11, 12)


def _t(**kw):
    d = dict(categoria="reagendamento", urgencia="media", resumo="x", cargas=[], acao_sugerida="x",
             informacao_faltando=[], rascunho_resposta="x")
    d.update(kw)
    return Triagem(**d)


class TestRegras(unittest.TestCase):
    def test_dias_uteis(self):
        self.assertEqual(dias_uteis_ate(date(2026, 11, 13), date(2026, 11, 16)), 1)  # sex -> seg
        self.assertEqual(dias_uteis_ate(HOJE, date(2026, 11, 10)), -2)

    def test_agenda_divergente(self):
        t = _t(cargas=[Carga(oc="120101", cliente=None, data_agenda="24/11/2026", hora_agenda="07:00", senha_agenda="88213")])
        self.assertTrue(any("sistema está 17/11/2026" in a for a in conferir(t, BASE, HOJE)))

    def test_contratando_perto_da_data(self):
        t = _t(categoria="agenda_confirmada",
               cargas=[Carga(oc="120230", cliente=None, data_agenda="14/11/2026", hora_agenda="08:30", senha_agenda="4471")])
        al = conferir(t, BASE, HOJE)
        self.assertTrue(any("NÃO contratado" in a for a in al))
        self.assertTrue(any("ainda não lançada" in a for a in al))

    def test_expedido_e_sem_oc_e_inexistente(self):
        t = _t(cargas=[Carga(oc="120344", cliente=None, data_agenda="21/11/2026", hora_agenda="10:00", senha_agenda=None)])
        self.assertTrue(any("já foi expedida" in a for a in conferir(t, BASE, HOJE)))
        self.assertTrue(any("nenhuma O.C." in a for a in conferir(_t(), BASE, HOJE)))
        t = _t(cargas=[Carga(oc="999999", cliente=None, data_agenda=None, hora_agenda=None, senha_agenda=None)])
        self.assertTrue(any("não encontrada" in a for a in conferir(t, BASE, HOJE)))


class TestChamadaAPI(unittest.TestCase):
    """Confere o que vai para a API e o fluxo completo até o HTML, com resposta falsa."""

    def setUp(self):
        self.pedidos = []
        resposta = _t(categoria="reagendamento", urgencia="alta", resumo="Reagendar 120101/120102 para 24/11",
                      cargas=[Carga(oc="120101", cliente="MERCADO FICTICIO NORTE", data_agenda="24/11/2026",
                                    hora_agenda="07:00", senha_agenda="88213")])

        def responder(req: httpx.Request):
            self.pedidos.append(json.loads(req.content))
            return httpx.Response(200, json={
                "id": "msg_teste", "type": "message", "role": "assistant", "model": triagem.MODELO,
                "content": [{"type": "text", "text": resposta.model_dump_json()}],
                "stop_reason": "end_turn", "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 10}})

        self.client = anthropic.Anthropic(api_key="teste", max_retries=0,
                                          http_client=httpx.Client(transport=httpx.MockTransport(responder)))

    def test_requisicao(self):
        t = triagem.triar(self.client, "e-mail de teste")
        self.assertEqual(t.cargas[0].senha_agenda, "88213")
        body = self.pedidos[0]
        self.assertEqual(body["model"], "claude-opus-5-5")
        self.assertEqual(body["fallbacks"], "default")
        self.assertEqual(body["output_config"]["effort"], "medium")
        self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
        self.assertIn("Nunca invente", body["system"] if isinstance(body["system"], str) else json.dumps(body["system"]))

    def test_fluxo_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = triagem.main([str(RAIZ / "exemplos" / "emails"), str(RAIZ / "exemplos" / "base_cargas.csv"),
                               "--saida", tmp, "--hoje", "12/11/2026"], client=self.client)
            self.assertEqual(rc, 0)
            pagina = (Path(tmp) / "triagem.html").read_text(encoding="utf-8")
            self.assertIn("sistema está 17/11/2026", pagina)
            self.assertEqual(len(self.pedidos), 5)


if __name__ == "__main__":
    unittest.main()
