import requests
import asyncio
import websockets
import json
import heapq

# Correct WebSocket API URL
API_URL = "ws://localhost:8000/ws/3F4365C5-77F1-405E-A6F2-66BE20521A40/0"
ARQUIVO_GRUPOS = "grupos.txt"

# Create a new group and save it to a file
def criar_grupo(nome):
    with open(ARQUIVO_GRUPOS, 'a') as arquivo:
        arquivo.write(f"{nome}\n")

    response = requests.post("http://localhost:8000/grupo", json={"Nome": nome})  # Key should be "Nome"

    print("Corpo da resposta:", response.text)

    if response.status_code == 200:
        try:
            return response.json()["Id"]  # Changed to "Id"
        except ValueError:
            print("Erro ao decodificar JSON:", response.text)
            return None
    else:
        print(f"Erro: {response.status_code}, Mensagem: {response.text}")
        return None

# Start the challenge for the created group
def iniciar_desafio(grupo_id):
    print(f"Solicitando iniciar desafio para o grupo ID: {grupo_id}")
    try:
        response = requests.get(f"http://localhost:8000/iniciar/{grupo_id}")

        # Check if the response status is successful
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        # Check if response has JSON content
        if response.headers['Content-Type'] == 'application/json':
            data = response.json()
            if data is not None:
                conexao = data.get("Conexao")
                if conexao is not None:
                    return conexao
                else:
                    print("Chave 'Conexao' não encontrada na resposta:", data)
            else:
                print("Resposta JSON está vazia ou não é válida:", data)
        else:
            print("Resposta não é JSON:", response.text)

    except requests.exceptions.HTTPError as http_err:
        print(f"Erro HTTP ao iniciar o desafio: {http_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"Erro ao conectar ao servidor: {req_err}")
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")

    return None


# Consult available mazes for the group
def consultar_labirintos(grupo_id):
    response = requests.get(f"http://localhost:8000/labirintos/{grupo_id}")
    if response.status_code == 200:
        return response.json().get("Labirintos", [])
    else:
        print(f"Erro ao consultar labirintos: {response.status_code}, Mensagem: {response.text}")
        return []

# Dijkstra's algorithm implementation to find the shortest path
def dijkstra(grafo, inicio, saida):
    fila_prioridade = []
    heapq.heappush(fila_prioridade, (0, inicio))
    distancias = {v: float('inf') for v in grafo}
    distancias[inicio] = 0
    caminho = {inicio: None}

    while fila_prioridade:
        distancia_atual, vertice_atual = heapq.heappop(fila_prioridade)

        if vertice_atual == saida:
            break

        for vizinho, peso in grafo[vertice_atual].items():
            distancia = distancia_atual + peso

            if distancia < distancias[vizinho]:
                distancias[vizinho] = distancia
                caminho[vizinho] = vertice_atual
                heapq.heappush(fila_prioridade, (distancia, vizinho))

    return caminho, distancias

# Async function to explore the maze through WebSocket
async def explorar_labirinto(websocket_url, entrada_id):
    async with websockets.connect(websocket_url) as websocket:
        init_message = f"ir:{entrada_id}"  # Correct command format
        await websocket.send(init_message)
        print("Iniciando exploração do labirinto...")

        grafo = {}
        saida = None

        while True:
            response = await websocket.recv()
            data = json.loads(response)

            vertice_atual = data["IdLabirinto"]  # Changed to "IdLabirinto"
            adjacencias = data["Adjacencia"]  # Changed to "Adjacencia"
            grafo[vertice_atual] = {adj: 1 for adj in adjacencias}

            print(f"Visitando vértice {vertice_atual} com adjacências: {data['Adjacencia']}")

            if data["Tipo"] == 1:  # Exit found
                print(f"Saída encontrada no vértice {vertice_atual}!")
                saida = vertice_atual
                break

            for adj in adjacencias:
                if adj not in grafo:
                    grafo[adj] = {}

            # Move to the next vertex if available
            if adjacencias:
                proximo_vertice = adjacencias[0]
                move_message = f"ir:{proximo_vertice}"
                await websocket.send(move_message)
                print(f"Movendo-se para o vértice {proximo_vertice}")
            else:
                print("Não há vizinhos disponíveis. Encerrando a exploração.")
                break

        if saida:
            print("Aplicando Dijkstra...")
            caminho_dijkstra, distancias = dijkstra(grafo, entrada_id, saida)

            caminho = []
            vertice = saida
            while vertice is not None:
                caminho.append(vertice)
                vertice = caminho[vertice] if vertice in caminho else None
            caminho.reverse()

            print("Caminho mais curto até a saída:", caminho)
            print("Distâncias a partir da entrada:", distancias)

# Main execution flow
if __name__ == "__main__":
    nome_grupo = "Grupo de Desafio"

    grupo_id = criar_grupo(nome_grupo)
    print(f"Grupo criado com ID: {grupo_id}")

    websocket_url = iniciar_desafio(grupo_id)
    print(f"WebSocket URL: {websocket_url}")

    labirintos = consultar_labirintos(grupo_id)
    print("Labirintos disponíveis:")
    for labirinto in labirintos:
        print(labirinto)

    if labirintos:
        entrada_id = labirintos[0]["Entrada"]  # Adjusting the key to match your LabirintoModel
        asyncio.run(explorar_labirinto(websocket_url, entrada_id))
    else:
        print("Nenhum labirinto disponível para explorar.")