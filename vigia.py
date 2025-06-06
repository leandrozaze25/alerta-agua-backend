import requests
import json
import time
import os
import redis
import firebase_admin
from firebase_admin import credentials, messaging

# --- CONFIGURAÇÕES ---
# O Render vai fornecer esta URL como uma variável de ambiente
REDIS_URL = os.getenv('REDIS_URL')
# A chave que o Redis vai usar para guardar a informação
REDIS_CHAVE_STATUS = "sanepar_status_atual"

URL_API_SANEPAR = "https://sgcb2b.sanepar.com.br/saneparmobile/ServiceFaltaDAgua.svc/webhttp/GetFaltaDAgua/51b27bf3-acec-4861-b80c-254a2a2d52d1/daced9a77c753388"
HEADERS = {'User-Agent': 'Mozilla/5.0'}
INTERVALO_DE_VERIFICACAO_SEGUNDOS = 1800 # 30 minutos

# --- CONFIGURAÇÃO DO FIREBASE ---
CAMINHO_DA_CHAVE_SECRETA = '/etc/secrets/serviceAccountKey.json'
TOKEN_DO_DISPOSITIVO_ALVO = "ff8MLprNSxefrMYN6a0elg:APA91bFjsTJ0zQT_GoQnTb5XMT7dF5rhHfyF0RltLi5gWWNVIv74SwcEZ9BZs081XH1_L4AhuFIu4Cw5awgI_5zwVCTXBq6O2yDs3z0bfAsM3eTui40CHv4" # O TEU TOKEN

try:
    cred = credentials.Certificate(CAMINHO_DA_CHAVE_SECRETA)
    firebase_admin.initialize_app(cred)
    print("VIGIA_FIREBASE: SDK Admin inicializado com sucesso!")
except Exception as e:
    print(f"VIGIA_FIREBASE: ERRO ao inicializar SDK: {e}")

# --- Conexão com o Redis ---
try:
    cliente_redis = redis.from_url(REDIS_URL, decode_responses=True)
    cliente_redis.ping()
    print("VIGIA_REDIS: Conexão com Redis bem-sucedida!")
except Exception as e:
    print(f"VIGIA_REDIS: ERRO de conexão com Redis: {e}")
    cliente_redis = None

def enviar_notificacao_fcm(titulo, corpo):
    if not firebase_admin._apps: return
    print(f"VIGIA_FCM: A enviar notificação: '{corpo}'")
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=titulo, body=corpo),
            token=TOKEN_DO_DISPOSITIVO_ALVO,
        )
        response = messaging.send(message)
        print(f"VIGIA_FCM: Mensagem enviada com sucesso: {response}")
    except Exception as e:
        print(f"VIGIA_FCM: Erro ao enviar mensagem: {e}")

def verificar_sanepar():
    if not cliente_redis:
        print("VIGIA: Sem conexão com Redis. A abortar verificação.")
        return

    print("VIGIA: Buscando status na Sanepar...")
    try:
        resposta = requests.get(URL_API_SANEPAR, headers=HEADERS, timeout=15)
        resposta.raise_for_status() # Lança erro se status não for 200

        novo_status_json = resposta.text # Guardamos o JSON como texto puro
        novo_status_dict = json.loads(novo_status_json)
        mensagem_nova = novo_status_dict.get("Mensagem", "")

        # Busca o status antigo guardado no Redis
        status_antigo_json = cliente_redis.get(REDIS_CHAVE_STATUS)
        mensagem_antiga = ""
        if status_antigo_json:
            mensagem_antiga = json.loads(status_antigo_json).get("Mensagem", "")

        if not status_antigo_json or mensagem_nova != mensagem_antiga:
            print(f"!!! MUDANÇA DETETADA: De '{mensagem_antiga}' para '{mensagem_nova}' !!!")
            # Guarda o novo status no Redis
            cliente_redis.set(REDIS_CHAVE_STATUS, novo_status_json)
            print("VIGIA_REDIS: Novo status guardado no Redis.")
            
            # Envia notificação apenas se não for a primeira vez
            if status_antigo_json:
                enviar_notificacao_fcm("Alerta de Água SJP", f"Novo status: {mensagem_nova}")
        else:
            print("VIGIA: Status inalterado.")

    except Exception as e:
        print(f"VIGIA: Erro durante a verificação: {e}")

if __name__ == '__main__':
    while True:
        verificar_sanepar()
        print(f"VIGIA: A aguardar {INTERVALO_DE_VERIFICACAO_SEGUNDOS} segundos para a próxima verificação.")
        time.sleep(INTERVALO_DE_VERIFICACAO_SEGUNDOS)

