from flask import Flask, jsonify
import requests
import json
import os
import redis
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials, messaging

# --- CONFIGURAÇÕES ---
REDIS_URL = os.getenv('REDIS_URL')
REDIS_CHAVE_STATUS = "sanepar_status_json"
REDIS_CHAVE_TIMESTAMP = "sanepar_timestamp"
TEMPO_CACHE_SEGUNDOS = 1800 # 30 minutos

URL_API_SANEPAR = "https://sgcb2b.sanepar.com.br/saneparmobile/ServiceFaltaDAgua.svc/webhttp/GetFaltaDAgua/51b27bf3-acec-4861-b80c-254a2a2d52d1/daced9a77c753388"
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# !!! SUBSTITUA PELO TEU TOKEN REAL !!!
TOKEN_DO_DISPOSITIVO_ALVO = "ff8MLprNSxefrMYN6a0elg:APA91bFjsTJ0zQT_GoQnTb5XMT7dF5rhHfyF0RltLi5gWWNVIv74SwcEZ9BZs081XH1_L4AhuFIu4Cw5awgI_5zwVCTXBq6O2yDs3z0bfAsM3eTui40CHv4"

# --- CONFIGURAÇÃO DO FIREBASE ---
CAMINHO_DA_CHAVE_SECRETA = '/etc/secrets/serviceAccountKey.json'
try:
    cred = credentials.Certificate(CAMINHO_DA_CHAVE_SECRETA)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    print("FIREBASE: SDK Admin inicializado com sucesso!")
except Exception as e:
    print(f"FIREBASE: ERRO ao inicializar SDK: {e}")

# --- Conexão com o Redis ---
try:
    cliente_redis = redis.from_url(REDIS_URL)
    cliente_redis.ping()
    print("API_REDIS: Conexão com Redis bem-sucedida!")
except Exception as e:
    print(f"API_REDIS: ERRO de conexão com Redis: {e}")
    cliente_redis = None

# --- Aplicação Flask ---
app = Flask(__name__)

def enviar_notificacao_fcm(titulo, corpo):
    if not firebase_admin._apps:
        print("FCM: Firebase não inicializado, notificação cancelada.")
        return
    
    print(f"FCM: A tentar enviar notificação: '{corpo}'")
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=titulo, body=corpo),
            token=TOKEN_DO_DISPOSITIVO_ALVO,
        )
        response = messaging.send(message)
        print(f"FCM: Mensagem enviada com sucesso: {response}")
    except Exception as e:
        print(f"FCM: Erro ao enviar mensagem: {e}")

def buscar_e_guardar_dados_sanepar():
    print("CACHE_MISS: A buscar dados novos na Sanepar...")
    try:
        resposta = requests.get(URL_API_SANEPAR, headers=HEADERS, timeout=15)
        resposta.raise_for_status()

        dados_novos_json = resposta.text
        dados_novos_dict = json.loads(dados_novos_json)
        mensagem_nova = dados_novos_dict.get("Mensagem", "")

        status_antigo_json = cliente_redis.get(REDIS_CHAVE_STATUS)
        houve_mudanca = False
        # Só consideramos uma mudança se já existia um status antigo
        if status_antigo_json:
            mensagem_antiga = json.loads(status_antigo_json.decode('utf-8')).get("Mensagem", "")
            if mensagem_nova != mensagem_antiga:
                houve_mudanca = True
                print(f"!!! MUDANÇA DETETADA: De '{mensagem_antiga}' para '{mensagem_nova}' !!!")
        
        # Guarda os novos dados e o timestamp no Redis de qualquer forma
        agora_timestamp = datetime.utcnow().isoformat()
        with cliente_redis.pipeline() as pipe:
            pipe.set(REDIS_CHAVE_STATUS, dados_novos_json)
            pipe.set(REDIS_CHAVE_TIMESTAMP, agora_timestamp)
            pipe.execute()
        print("CACHE_MISS: Dados novos e timestamp guardados no Redis.")

        # Se houve mudança, envia a notificação
        if houve_mudanca:
            enviar_notificacao_fcm("Alerta de Água SJP", f"Novo status: {mensagem_nova}")
            
        return dados_novos_dict

    except Exception as e:
        print(f"ERRO: Falha ao buscar dados da Sanepar: {e}")
        return {"erro": f"Não foi possível contactar o serviço da Sanepar."}


@app.route('/status_agua')
def get_status_agua():
    if not cliente_redis:
        return jsonify({"erro": "Serviço temporariamente indisponível."}), 503

    ultimo_timestamp_str = cliente_redis.get(REDIS_CHAVE_TIMESTAMP)
    status_guardado_json = cliente_redis.get(REDIS_CHAVE_STATUS)

    if ultimo_timestamp_str and status_guardado_json:
        ultimo_timestamp = datetime.fromisoformat(ultimo_timestamp_str.decode('utf-8'))
        tempo_passado = datetime.utcnow() - ultimo_timestamp
        if tempo_passado < timedelta(seconds=TEMPO_CACHE_SEGUNDOS):
            print("CACHE_HIT: A retornar dados do cache Redis.")
            return jsonify(json.loads(status_guardado_json.decode('utf-8')))

    dados_novos = buscar_e_guardar_dados_sanepar()
    return jsonify(dados_novos)

@app.route('/')
def pagina_principal():
    return "<h1>Servidor Alerta de Água SJP (com notificações) está no ar!</h1>"
