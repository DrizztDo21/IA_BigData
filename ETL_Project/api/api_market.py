from fastapi import FastAPI
import random
import uuid
from datetime import datetime
import asyncio
from sse_starlette.sse import EventSourceResponse
import json

app = FastAPI()

# ==========================================
# ESTADO GLOBAL Y ENTIDADES DE FRAUDE
# ==========================================
MODO_ATAQUE = False

PAYS = ["ES", "UK", "US", "IT", "FR", "DE"]

# Definimos los nodos de nuestro "Anillo de Fraude" para el Grafo Tripartito
BANDA_CRIMINAL = ["FRAUD_USER_1", "FRAUD_USER_2", "FRAUD_USER_3", "FRAUD_USER_4", "FRAUD_USER_5"]
IPS_BOTNET = ["222.15.1.1", "222.15.1.2", "222.15.1.3"]
PAISES_SANCIONADOS = ["RU", "CN"]

@app.get("/stream/visitas")
async def stream_clicks():
    async def event_generator():
        while True:
            delay = random.uniform(0.01, 0.05) if MODO_ATAQUE else random.uniform(0.5, 1.5)
            await asyncio.sleep(delay)
            
            if MODO_ATAQUE:
                # Utilizamos usuarios de la banda criminal, IPs de la botnet y un comportamiento típico de scraper agresivo (muchas páginas en poco tiempo)
                data = {
                    "timestamp": datetime.now().isoformat(),
                    "user_id": random.choice(BANDA_CRIMINAL),
                    "ip": random.choice(IPS_BOTNET),
                    "session_duration": random.randint(1, 3),
                    "pages_visited": random.randint(80, 150),
                    "is_bot": True,
                    "flag_ataque": True
                }
            else:
                # COMPORTAMIENTO NORMAL + SCRAPER SIGILOSO (Para la capa Batch)
                if random.random() < 0.10:
                    data = {
                        "timestamp": datetime.now().isoformat(),
                        "user_id": f"GUEST_{random.randint(100, 999)}", 
                        "ip": "45.33.22.11", # IP FIJA (Bot lento)
                        "session_duration": random.randint(10, 25), 
                        "pages_visited": random.randint(2, 5), 
                        "is_bot": False, 
                        "flag_ataque": False
                    }
                else:
                    data = {
                        "timestamp": datetime.now().isoformat(),
                        "user_id": str(uuid.uuid4())[:8],
                        "ip": f"192.168.1.{random.randint(1, 254)}",
                        "session_duration": random.randint(60, 600),
                        "pages_visited": random.randint(1, 10),
                        "is_bot": random.random() < 0.05,
                        "flag_ataque": False
                    }

            yield f"{json.dumps(data)}\n"

    return EventSourceResponse(event_generator())

@app.get("/pagos")
def get_payments():
    if MODO_ATAQUE:
        # Simulación de transacciones fraudulentas: Usuarios de la banda criminal, países sancionados y métodos de pago sospechosos (Crypto)
        return {
            "tx_id": str(uuid.uuid4()),
            "user_id": random.choice(BANDA_CRIMINAL),
            "amount": round(random.uniform(2000.0, 5000.0), 2),
            "currency": "EUR",
            "card_country": random.choice(PAISES_SANCIONADOS), 
            "method": "Crypto",
            "flag_ataque": True
        }
    else:
        return {
            "tx_id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4())[:8],
            "amount": round(random.uniform(5.0, 1000.0), 2),
            "currency": "EUR",
            "card_country": random.choice(PAYS),
            "method": random.choice(["VISA", "MasterCard", "PayPal"]),
            "flag_ataque": False
        }

# --- ENDPOINTS DE CONTROL ---
@app.get("/ataque/on")
def activar_ataque():
    global MODO_ATAQUE
    MODO_ATAQUE = True
    return {"status": "MODO ATAQUE ACTIVADO: Botnet inyectando fraude estructurado."}

@app.get("/ataque/off")
def desactivar_ataque():
    global MODO_ATAQUE
    MODO_ATAQUE = False
    return {"status": "MODO NORMAL restaurado."}