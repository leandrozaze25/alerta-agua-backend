from flask import Flask, jsonify
import requests
import json
import os
import redis
from datetime import datetime, timedelta

# --- CONFIGURAÇÕES ---
REDIS_URL = os.getenv('REDIS_URL')
# A chave que o Redis vai usar para guardar o JSON com o status
REDIS_CHAVE_STATUS = "sanepar_status_json"
# Uma nova chave para guardar a data da última verificação
REDIS_CHAVE_TIMESTAMP = "sanepar_timestamp"

# Define o tempo de "validade" do cache em segundos (30 minutos)
TEMPO_CACHE_SEGUNDOS = 1800

URL_API_SANEPAR = "https://sgcb2b.sanepar.com.br/saneparmobile/ServiceFaltaDAgua.svc/webhttp/GetFaltaDAgua/51b27bf3-acec-4861-b80c-254a2a2d52d1/daced9a77c753388"
HEADERS = {'User-Agent': 'Mozilla/5.0'}

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

def buscar_e_guardar_dados_sanepar():
    """Esta função busca os dados da Sanepar e os guarda no Redis."""
    print("CACHE_MISS: A buscar dados novos na Sanepar...")
    try:
        resposta = requests.get(URL_API_SANEPAR, headers=HEADERS, timeout=15)
        resposta.raise_for_status() # Lança erro se o status não for 200

        dados_json = resposta.text
        # Guarda os novos dados e o timestamp atual no Redis
        agora_timestamp = datetime.utcnow().isoformat()
        
        # Usamos uma transação para garantir que ambos os valores são guardados
        with cliente_redis.pipeline() as pipe:
            pipe.set(REDIS_CHAVE_STATUS, dados_json)
            pipe.set(REDIS_CHAVE_TIMESTAMP, agora_timestamp)
            pipe.execute()
            
        print("CACHE_MISS: Dados novos e timestamp guardados no Redis.")
        return json.loads(dados_json)

    except Exception as e:
        print(f"ERRO: Falha ao buscar dados da Sanepar: {e}")
        # Retorna um erro que pode ser mostrado ao utilizador
        return {"erro": "Não foi possível contactar o serviço da Sanepar."}


@app.route('/status_agua')
def get_status_agua():
    if not cliente_redis:
        return jsonify({"erro": "Serviço temporariamente indisponível."}), 503

    try:
        # Pega a data da última verificação e o status guardado
        ultimo_timestamp_str = cliente_redis.get(REDIS_CHAVE_TIMESTAMP)
        status_guardado_json = cliente_redis.get(REDIS_CHAVE_STATUS)

        if ultimo_timestamp_str and status_guardado_json:
            ultimo_timestamp = datetime.fromisoformat(ultimo_timestamp_str.decode('utf-8'))
            tempo_passado = datetime.utcnow() - ultimo_timestamp
            
            # Se os dados no cache ainda são recentes (menos de 30 min)
            if tempo_passado < timedelta(seconds=TEMPO_CACHE_SEGUNDOS):
                print("CACHE_HIT: A retornar dados do cache Redis.")
                return jsonify(json.loads(status_guardado_json.decode('utf-8')))

        # Se não houver cache ou se o cache estiver desatualizado, busca novos dados
        dados_novos = buscar_e_guardar_dados_sanepar()
        return jsonify(dados_novos)

    except Exception as e:
        print(f"ERRO: Erro ao processar o pedido: {e}")
        return jsonify({"erro": f"Erro interno do servidor: {e}"}), 500

@app.route('/')
def pagina_principal():
    return "<h1>Servidor Alerta de Água SJP está no ar!</h1>"

# Não precisamos da parte de firebase-admin ou do vigia contínuo aqui.
# A notificação será uma evolução futura, se desejado.
