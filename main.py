import asyncio
import websockets
import json
import logging
from collections import deque

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

websocket_url = "ws://localhost:8000/ws/3F4365C5-77F1-405E-A6F2-66BE20521A40/0"
semaforo = asyncio.Semaphore(10)  # Limite de 10 conexões simultâneas

init_message = {
    "Evento": "Ir",
    "VerticeId": 0  # Define the starting vertex
}

async def connect_with_retry(url, retries=5, delay=2):
    for tentativa in range(retries):
        try:
            websocket = await websockets.connect(url)
            return websocket
        except Exception as e:
            logging.warning(f"Falha na conexão: {e}. Tentando novamente em {delay} segundos...")
            await asyncio.sleep(delay)
    raise ConnectionError("Não foi possível conectar ao WebSocket após várias tentativas.")

async def explore_maze():
    async with semaforo:
        try:
            websocket = await connect_with_retry(websocket_url)
        except ConnectionError as e:
            logging.error(e)
            return

        labirinto = {}
        visitados = set()
        fila = deque([init_message["VerticeId"]])

        await websocket.send(json.dumps(init_message))
        logging.info("Iniciando exploração do labirinto...")

        while fila:
            vertice_atual = fila.popleft()
            if vertice_atual in visitados:
                continue
            visitados.add(vertice_atual)

            move_message = {
                "Evento": "Ir",
                "VerticeId": vertice_atual
            }
            await websocket.send(json.dumps(move_message))
            logging.info(f"Movendo-se para o vértice {vertice_atual}")

            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=10)
            except asyncio.TimeoutError:
                logging.warning(f"Timeout ao receber resposta para o vértice {vertice_atual}")
                continue

            data = json.loads(response)
            labirinto[vertice_atual] = data.get("Adjacencia", [])
            logging.info(f"Visitando vértice {vertice_atual} com adjacências: {data.get('Adjacencia', [])}")

            if data.get("Tipo") == 1:  # Assuming '1' indicates an exit
                logging.info(f"Saída encontrada no vértice {vertice_atual}!")
                break

            for vizinho in data.get("Adjacencia", []):
                if vizinho not in visitados:
                    fila.append(vizinho)

        else:
            logging.info("Exploração completa, sem mais vértices para visitar.")

        await websocket.close()

async def main():
    tarefas = [explore_maze() for _ in range(100)]  # Exemplo com 100 conexões
    await asyncio.gather(*tarefas)

if __name__ == "__main__":
    asyncio.run(main())
