import requests
import json
import time
import threading
from flask import Flask, jsonify
import firebase_admin
from firebase_admin import credentials, messaging

# --- CONFIGURAÇÕES ---
URL_API_SANEPAR = "https://sgcb2b.sanepar.com.br/saneparmobile/ServiceFaltaDAgua.svc/webhttp/GetFaltaDAgua/51b27bf3-acec-4861-b80c-254a2a2d52d1/daced9a77c753388"
HEADERS = {'User-Agent': 'Mozilla/5.0'}
INTERVALO_DE_VERIFICACAO_SEGUNDOS = 1800 # 30 minutos

# !!! IMPORTANTE: Substitui este token pelo token REAL do teu dispositivo S20
TOKEN_DO_DISPOSITIVO_ALVO = "ff8MLprNSxefrMYN6a0elg:APA91bFjsTJ0zQT_GoQnTb5XMT7dF5rhHfyF0RltLi5gWWNVIv74SwcEZ9BZs081XH1_L4AhuFIu4Cw5awgI_5zwVCTXBq6O2yDs3z0bfAsM3eTui40CHv4" # O TEU TOKEN REAL AQUI

# --- CONFIGURAÇÃO DO FIREBASE ---
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    print("FIREBASE: SDK Admin inicializado com sucesso!")
except Exception as e:
    print(f"FIREBASE: ERRO ao inicializar o SDK Admin - {e}")

# --- LÓGICA DO SERVIDOR ---
app = Flask(__name__)
ultimo_status_conhecido = {}
lock = threading.Lock()

def enviar_notificacao_fcm(titulo, corpo):
    if not firebase_admin._apps: return
    print(f"FCM: A tentar enviar notificação: '{titulo}'")
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=titulo, body=corpo),
            token=TOKEN_DO_DISPOSITIVO_ALVO,
        )
        response = messaging.send(message)
        print(f"FCM: Mensagem enviada com sucesso: {response}")
    except Exception as e:
        print(f"FCM: Erro ao enviar mensagem: {e}")

def verificar_sanepar():
    global ultimo_status_conhecido
    while True:
        print("VIGIANDO: Buscando status na Sanepar...")
        try:
            resposta = requests.get(URL_API_SANEPAR, headers=HEADERS, timeout=15)
            if resposta.status_code == 200:
                novo_status = resposta.json()
                mensagem_nova = novo_status.get("Mensagem", "")
                with lock:
                    mensagem_antiga = ultimo_status_conhecido.get("Mensagem", "")
                    if not ultimo_status_conhecido or mensagem_nova != mensagem_antiga:
                        print(f"!!! MUDANÇA DETETADA: De '{mensagem_antiga}' para '{mensagem_nova}' !!!")
                        ultimo_status_conhecido = novo_status
                        # Não envia notificação na primeira vez, apenas guarda o estado
                        if mensagem_antiga:
                            enviar_notificacao_fcm("Alerta de Água SJP", f"Novo status: {mensagem_nova}")
                    else:
                        print("VIGIANDO: Status inalterado.")
            else:
                print(f"VIGIANDO: Erro ao contactar Sanepar. Código: {resposta.status_code}")
        except Exception as e:
            print(f"VIGIANDO: Erro de rede: {e}")

        time.sleep(INTERVALO_DE_VERIFICACAO_SEGUNDOS)

@app.route('/status_agua')
def get_status_agua():
    print("APP_REQUEST: Pedido recebido.")
    with lock:
        if not ultimo_status_conhecido:
            return jsonify({"Mensagem": "Servidor a iniciar, aguarde a primeira verificação."})
        return jsonify(ultimo_status_conhecido)

@app.route('/')
def health_check():
    return "Servidor Alerta de Água SJP está no ar!"

# Inicia o vigia numa thread separada quando o servidor começa
vigia_thread = threading.Thread(target=verificar_sanepar, daemon=True)
vigia_thread.start()