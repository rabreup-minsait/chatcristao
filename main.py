from database import SessionLocal, Usuario
import warnings
import os
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

import httpx
import unicodedata
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    http_client=httpx.Client(verify=False)
)

VECTOR_STORE_ID = "vs_69e02188f9848191ae0f57b865c9495c"


def normalizar(texto):
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.lower()
    if texto.endswith("s"):
        texto = texto[:-1]
    return texto


perfil = {
    "nome": None,
    "gostos": []
}

mensagens = [
    {
        "role": "system",
        "content": (
            "Você é uma assistente cristã, direta, acolhedora, objetivo e carinhosa. "
            "Responda apenas sobre assuntos bíblicos e cristãos, usando a Bíblia como base principal. "
            "Use o conteúdo encontrado no acervo bíblico para responder. "
            "Se a pergunta não for relacionada à Bíblia, fé cristã, personagens bíblicos, versículos, "
            "ensinamentos cristãos ou temas religiosos, diga com gentileza que você só responde "
            "assuntos bíblicos e cristãos. "
            "Não invente versículos. Se não encontrar base suficiente, diga isso claramente."
        )
    }
]


class Pergunta(BaseModel):
    texto: str


@app.get("/")
def raiz():
    return {"mensagem": "API do Chatbot funcionando!"}


@app.post("/chat")
def chat(pergunta: Pergunta):
    global perfil, mensagens

    db = SessionLocal()

    texto_original = pergunta.texto.strip()
    texto_usuario = texto_original.lower()

    if not texto_original:
        return {"resposta": ""}

    if texto_usuario == "limpar memoria":
        perfil["nome"] = None
        perfil["gostos"] = []
        return {"resposta": "Pronto! Esqueci tudo sobre você. Pode começar do zero!"}

    if "deus abençoe" in texto_usuario:
        return {"resposta": "Amém, você também!"}

    gatilho_nome = None
    if "meu nome é" in texto_usuario:
        gatilho_nome = "meu nome é"
    elif "eu me chamo" in texto_usuario:
        gatilho_nome = "eu me chamo"
    elif "pode me chamar de" in texto_usuario:
        gatilho_nome = "pode me chamar de"

    if gatilho_nome:
        novo_nome = texto_original.lower().split(gatilho_nome)[-1].strip().title()
        if perfil["nome"] == novo_nome:
            return {"resposta": f"Já sei que você se chama {novo_nome}!"}
        perfil["nome"] = novo_nome
        return {"resposta": f"Atualizado! Agora vou te chamar de {novo_nome}."}

    if "gosto de" in texto_usuario:
        gosto = texto_original.lower().split("gosto de")[-1].strip()
        if any(normalizar(g) == normalizar(gosto) for g in perfil["gostos"]):
            return {"resposta": f"Já sei que você gosta de {gosto}!"}
        perfil["gostos"].append(gosto)
        return {"resposta": f"Legal, vou lembrar que você gosta de {gosto}!"}

    if "quem eu sou" in texto_usuario:
        if perfil["nome"] and perfil["gostos"]:
            resposta = f"Você é {perfil['nome']} e gosta de {', '.join(perfil['gostos'])}."
        elif perfil["nome"]:
            resposta = f"Você é {perfil['nome']}, mas ainda não me contou o que gosta."
        elif perfil["gostos"]:
            resposta = f"Ainda não sei seu nome, mas sei que você gosta de {', '.join(perfil['gostos'])}."
        else:
            resposta = "Ainda não sei nada sobre você."
        return {"resposta": resposta}

    contexto_extra = ""
    if perfil["nome"]:
        contexto_extra += f"O nome do usuário é {perfil['nome']}. "
    if perfil["gostos"]:
        contexto_extra += f"O usuário gosta de: {', '.join(perfil['gostos'])}. "

    mensagens[0]["content"] = (
        "Você é um assistente cristão, direto e objetivo. "
        + contexto_extra +
        "Sempre escreva:"
        "- Deus, Jesus, Cristo, Espírito Santo com inicial maiúscula."
        "- Quando se referir a Deus, use maiúsculas (Senhor, Pai, Filho)."
        "Responda apenas sobre assuntos bíblicos e cristãos, usando a Bíblia como base principal. "
        "Use o conteúdo encontrado no acervo bíblico para responder. "
        "Se a pergunta não for relacionada à Bíblia, fé cristã, personagens bíblicos, versículos, "
        "ensinamentos cristãos ou temas religiosos, diga com gentileza que você só responde "
        "assuntos bíblicos e cristãos. "
        "Não invente versículos. Se não encontrar base suficiente, diga isso claramente."
    )

    mensagens.append({"role": "user", "content": texto_original})

    resposta = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "system",
                "content": mensagens[0]["content"]
            },
            {
                "role": "user",
                "content": texto_original
            }
        ],
        tools=[
            {
                "type": "file_search",
                "vector_store_ids": [VECTOR_STORE_ID]
            }
        ]
    )

    texto_resposta = resposta.output_text

    mensagens.append({"role": "assistant", "content": texto_resposta})

    if len(mensagens) > 10:
        mensagens = [mensagens[0]] + mensagens[-9:]

    return {"resposta": texto_resposta}