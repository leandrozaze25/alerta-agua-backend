from flask import Flask, jsonify
import os
import redis
import json

# --- CONFIGURAÇÕES ---
REDIS_URL = os.getenv('REDIS_URL')
REDIS_CHAVE_STATUS = "sanepar_status_atual"

# --- Conexão com o Redis ---
try:
    cliente_redis = redis.from_url(REDIS_URL, decode_responses=True)
    cliente_redis.ping()
    print("API_REDIS: Conexão com Redis bem-sucedida!")
except Exception as e:
    print(f"API_REDIS: ERRO de conexão com Redis: {e}")
    cliente_redis = None

# Cria a aplicação Flask
app = Flask(__name__)

@app.route('/status_agua')
def get_status_agua():
    if not cliente_redis:
        return jsonify({"erro": "Serviço indisponível - não foi possível conectar à base de dados."}), 503

    status_guardado_json = cliente_redis.get(REDIS_CHAVE_STATUS)

    if status_guardado_json:
        # Retorna os dados que o vigia guardou
        return jsonify(json.loads(status_guardado_json))
    else:
        # Se o vigia ainda não guardou nada
        return jsonify({"Mensagem": "A aguardar a primeira verificação do sistema de monitorização."})

@app.route('/')
def pagina_principal():
    return "<h1>Servidor Alerta de Água SJP no ar!</h1>"
