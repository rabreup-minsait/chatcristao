from database import SessionLocal, Usuario
import warnings
import os
import json
import re
import unicodedata

from dotenv import load_dotenv
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

warnings.filterwarnings("ignore")
load_dotenv()

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
    texto = texto.lower().strip()
    if texto.endswith("s"):
        texto = texto[:-1]
    return texto


def corrigir_termos_cristaos(texto):
    substituicoes = {
        r"\bdeus\b": "Deus",
        r"\bjesus\b": "Jesus",
        r"\bcristo\b": "Cristo",
        r"\besp[ií]rito santo\b": "Espírito Santo",
        r"\bsenhor\b": "Senhor",
        r"\bpai\b": "Pai",
        r"\bfilho\b": "Filho"
    }

    for padrao, substituto in substituicoes.items():
        texto = re.sub(padrao, substituto, texto, flags=re.IGNORECASE)

    return texto


def carregar_gostos(texto_gostos):
    if not texto_gostos:
        return []
    try:
        return json.loads(texto_gostos)
    except Exception:
        return []


def salvar_gostos(lista_gostos):
    return json.dumps(lista_gostos, ensure_ascii=False)


def buscar_ou_criar_usuario(db, user_id):
    usuario = db.query(Usuario).filter_by(user_id=user_id).first()

    if not usuario:
        usuario = Usuario(
            user_id=user_id,
            nome=None,
            gostos=salvar_gostos([])
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)

    return usuario


def montar_prompt_sistema(nome, gostos):
    contexto_extra = ""

    if nome:
        contexto_extra += f"O nome da usuária é {nome}. "
    if gostos:
        contexto_extra += f"A usuária gosta de: {', '.join(gostos)}. "

    return (
        "Você é uma assistente cristã, direta, acolhedora, objetiva e carinhosa. "
        "Sempre escreva Deus, Jesus, Cristo e Espírito Santo com inicial maiúscula. "
        "Quando se referir a Deus, use maiúsculas em Senhor, Pai e Filho. "
        + contexto_extra +
        "Responda apenas sobre assuntos bíblicos e cristãos, usando a Bíblia como base principal. "
        "Use o conteúdo encontrado no acervo bíblico para responder. "
        "Se a pergunta não for relacionada à Bíblia, fé cristã, personagens bíblicos, versículos, "
        "ensinamentos cristãos ou temas religiosos, diga com gentileza que você só responde "
        "assuntos bíblicos e cristãos. "
        "Não invente versículos. Se não encontrar base suficiente, diga isso claramente. "
        "Responda de forma natural, clara e não muito longa."
    )


class Pergunta(BaseModel):
    texto: str
    user_id: str | None = "default"


@app.get("/")
def raiz():
    return {"mensagem": "API do Chatbot funcionando!"}


@app.post("/chat")
def chat(pergunta: Pergunta):
    db = SessionLocal()

    try:
        texto_original = pergunta.texto.strip()
        texto_usuario = texto_original.lower()
        user_id = (pergunta.user_id or "default").strip()

        if not texto_original:
            return {"resposta": ""}

        usuario = buscar_ou_criar_usuario(db, user_id)

        nome = usuario.nome
        gostos = carregar_gostos(usuario.gostos)

        if texto_usuario == "limpar memoria":
            usuario.nome = None
            usuario.gostos = salvar_gostos([])
            db.commit()
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

            if usuario.nome == novo_nome:
                return {"resposta": f"Já sei que você se chama {novo_nome}!"}

            usuario.nome = novo_nome
            db.commit()
            return {"resposta": f"Atualizado! Agora vou te chamar de {novo_nome}."}

        if "gosto de" in texto_usuario:
            gosto = texto_original.lower().split("gosto de")[-1].strip()

            if any(normalizar(g) == normalizar(gosto) for g in gostos):
                return {"resposta": f"Já sei que você gosta de {gosto}!"}

            gostos.append(gosto)
            usuario.gostos = salvar_gostos(gostos)
            db.commit()
            return {"resposta": f"Legal, vou lembrar que você gosta de {gosto}!"}

        if "quem eu sou" in texto_usuario:
            if usuario.nome and gostos:
                resposta = f"Você é {usuario.nome} e gosta de {', '.join(gostos)}."
            elif usuario.nome:
                resposta = f"Você é {usuario.nome}, mas ainda não me contou do que gosta."
            elif gostos:
                resposta = f"Ainda não sei seu nome, mas sei que você gosta de {', '.join(gostos)}."
            else:
                resposta = "Ainda não sei nada sobre você."
            return {"resposta": resposta}

        prompt_sistema = montar_prompt_sistema(usuario.nome, gostos)

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "system",
                    "content": prompt_sistema
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

        texto_resposta = response.output_text
        texto_resposta = corrigir_termos_cristaos(texto_resposta)

        return {"resposta": texto_resposta}

    finally:
        db.close()