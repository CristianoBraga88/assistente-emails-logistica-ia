# -*- coding: utf-8 -*-
"""Formato (schema) que o Claude é obrigado a devolver para cada e-mail.

Usamos Pydantic + "structured outputs" da API: a resposta já chega validada,
sem precisar "caçar" JSON no meio do texto.
"""
from typing import Literal

from pydantic import BaseModel, Field

Categoria = Literal[
    "reagendamento",        # cliente/transportadora pede nova data
    "agenda_confirmada",    # chegou data/hora/senha de entrega
    "cobranca_status",      # alguém pergunta onde está a carga / previsão
    "problema_entrega",     # recusa, avaria, devolução, atraso
    "faturamento",          # NF, faturar O.C., cancelamento de nota
    "outro",
]


class Carga(BaseModel):
    oc: str = Field(description="Número da ordem de carga (O.C.) citado no e-mail, só dígitos. Ex.: '120345'.")
    cliente: str | None = Field(description="Nome do cliente se aparecer no e-mail; senão null.")
    data_agenda: str | None = Field(description="Data de entrega citada para ESTA carga, formato dd/mm/aaaa; null se não houver.")
    hora_agenda: str | None = Field(description="Hora citada, formato HH:MM; null se não houver.")
    senha_agenda: str | None = Field(description="Senha/ticket/voucher de agendamento, se houver; senão null.")


class Triagem(BaseModel):
    categoria: Categoria
    urgencia: Literal["alta", "media", "baixa"] = Field(
        description="alta = entrega em até 2 dias úteis, cliente parado ou problema; baixa = só informativo.")
    resumo: str = Field(description="Uma frase, em português, do que o e-mail pede.")
    cargas: list[Carga]
    acao_sugerida: str = Field(description="O que o analista deve fazer no sistema, em uma frase.")
    informacao_faltando: list[str] = Field(
        description="O que falta no e-mail para agir (ex.: 'hora da agenda', 'número da O.C.'). Lista vazia se nada.")
    rascunho_resposta: str = Field(description="Rascunho curto de resposta, neutro e educado. NÃO é enviado.")
