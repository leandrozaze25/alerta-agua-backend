from flask import Flask, jsonify
import requests
import json
import os
import redis
from datetime import datetime, timedelta

# --- CONFIGURAÇÕES ---
REDIS_URL = os.getenv('REDIS_URL')
REDIS_CHAVE_STATUS = "sanepar_status_json"
REDIS_CHAVE_TIMESTAMP = "sanepar_timestamp"
TEMPO_CACHE_SEGUNDOS = 1800

URL_API_SANEPAR = "https://sgcb2b.sanepar.com.br/saneparmobile/ServiceFaltaDAgua.svc/webhttp/GetFaltaDAgua/51b27bf3-acec-4861-b80c-254a2a2d52d1/daced9a77c753388"
HEADERS = {'User-Agent': 'Mozilla/5.0'}

# --- Conexão com o Redis ---
try:
    cliente_redis = redis.from_url(REDIS_URL, decode_responses=True)
    cliente_redis.ping()
    print("API_REDIS: Conexão com Redis bem-sucedida!")
except Exception as e:
    print(f"API_REDIS: ERRO de conexão com Redis: {e}")
    cliente_redis = None

# --- Aplicação Flask ---
app = Flask(__name__)

# --- Funções Auxiliares ---
def buscar_e_guardar_dados_sanepar():
    """Busca os dados da Sanepar e os guarda no Redis."""
    print("CACHE_MISS: A buscar dados novos na Sanepar...")
    try:
        resposta = requests.get(URL_API_SANEPAR, headers=HEADERS, timeout=15)
        resposta.raise_for_status()
        dados_json = resposta.text
        agora_timestamp = datetime.utcnow().isoformat()
        with cliente_redis.pipeline() as pipe:
            pipe.set(REDIS_CHAVE_STATUS, dados_json)
            pipe.set(REDIS_CHAVE_TIMESTAMP, agora_timestamp)
            pipe.execute()
        print("CACHE_MISS: Dados novos e timestamp guardados no Redis.")
        return json.loads(dados_json)
    except Exception as e:
        print(f"ERRO: Falha ao buscar dados da Sanepar: {e}")
        return {"erro": f"Não foi possível contactar o serviço da Sanepar: {str(e)}"}

# --- ROTAS DA API ---

@app.route('/')
def pagina_principal():
    return "<h1>Servidor Alerta de Água SJP está no ar!</h1>"

@app.route('/status_agua')
def get_status_agua():
    """Retorna o status atual, usando o cache ou buscando novos dados se o cache estiver velho."""
    if not cliente_redis:
        return jsonify({"erro": "Serviço temporariamente indisponível."}), 503

    ultimo_timestamp_str = cliente_redis.get(REDIS_CHAVE_TIMESTAMP)
    status_guardado_json = cliente_redis.get(REDIS_CHAVE_STATUS)

    if ultimo_timestamp_str and status_guardado_json:
        ultimo_timestamp = datetime.fromisoformat(ultimo_timestamp_str)
        tempo_passado = datetime.utcnow() - ultimo_timestamp
        if tempo_passado < timedelta(seconds=TEMPO_CACHE_SEGUNDOS):
            print("CACHE_HIT: A retornar dados do cache Redis.")
            return jsonify(json.loads(status_guardado_json))

    dados_novos = buscar_e_guardar_dados_sanepar()
    return jsonify(dados_novos)

# --- A NOSSA NOVA ROTA DE TESTE ---
@app.route('/forcar_verificacao')
def forcar_verificacao():
    """
    Esta rota secreta força uma nova busca na Sanepar e retorna o resultado.
    (No futuro, poderíamos protegê-la com uma senha).
    """
    print("DEBUG: Verificação forçada foi acionada!")
    dados_novos = buscar_e_guardar_dados_sanepar()
    return jsonify({
        "status": "Verificação forçada com sucesso.",
        "dados_recebidos": dados_novos
    })
