from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
import uuid
import asyncio
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, UUID as SQLUUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.schema import PrimaryKeyConstraint

Base = declarative_base()


# SQLAlchemy models
class Aresta(Base):
    __tablename__ = 'arestas'

    vertice_origem_id = Column(Integer, ForeignKey('vertices.id'), nullable=False)
    vertice_destino_id = Column(Integer, ForeignKey('vertices.id'), nullable=False)
    peso = Column(Integer, nullable=False)

    # Definindo a chave primária composta
    __table_args__ = (PrimaryKeyConstraint('vertice_origem_id', 'vertice_destino_id', name='pk_aresta'),)

    # Relacionamentos
    vertice_origem = relationship("Vertice", foreign_keys=[vertice_origem_id])
    vertice_destino = relationship("Vertice", foreign_keys=[vertice_destino_id])

    def __repr__(self):
        return f"<Aresta(origem={self.vertice_origem_id}, destino={self.vertice_destino_id}, peso={self.peso})>"


class Vertice(Base):
    __tablename__ = 'vertices'

    id = Column(Integer, nullable=False)
    labirinto_id = Column(Integer, ForeignKey('labirintos.id'), nullable=False)
    tipo = Column(Integer)

    labirinto = relationship("Labirinto", back_populates="vertices")

    # Relacionamento com a tabela Aresta para definir as adjacências
    arestas_origem = relationship("Aresta", foreign_keys=[Aresta.vertice_origem_id], back_populates="vertice_origem")
    arestas_destino = relationship("Aresta", foreign_keys=[Aresta.vertice_destino_id], back_populates="vertice_destino")

    __table_args__ = (PrimaryKeyConstraint('id', 'labirinto_id', name='pk_vertice'),)

    def __repr__(self):
        return f"<Vertice(id={self.id}, labirinto_id={self.labirinto_id})>"


class Labirinto(Base):
    __tablename__ = 'labirintos'

    id = Column(Integer, primary_key=True, autoincrement=True)
    vertices = relationship("Vertice", back_populates="labirinto")
    entrada = Column(Integer)
    dificuldade = Column(String)

    def __repr__(self):
        return f"<Labirinto(id={self.id}, entrada={self.entrada}, dificuldade={self.dificuldade})>"


class Grupo(Base):
    __tablename__ = 'grupos'

    id = Column(SQLUUID(as_uuid=True), primary_key=True)
    nome = Column(String)
    labirintos_concluidos = Column(String)  # Assuming labirintos_concluidos is stored as a comma-separated string


class SessaoWebSocket(Base):
    __tablename__ = 'sessoes_websocket'

    id = Column(Integer, primary_key=True, unique=True, autoincrement=True)
    grupo_id = Column(String, ForeignKey('grupos.id'))  # Use String type for UUID
    conexao = Column(String)


# Pydantic models
class VerticeModel(BaseModel):
    id: int
    labirintoId: int
    tipo: int


class ArestaModel(BaseModel):
    origemId: int
    destinoId: int
    peso: int


class LabirintoModel(BaseModel):
    vertices: List[VerticeModel]
    arestas: List[ArestaModel]
    entrada: int
    dificuldade: str


class GrupoModel(BaseModel):
    nome: str
    labirintos_concluidos: Optional[List[int]] = None


# DTOs
class VerticeDto(BaseModel):
    id: int
    adjacentes: List[int]
    tipo: int


class LabirintoDto(BaseModel):
    LabirintoId: int
    Dificuldade: str
    Completo: bool
    Passos: int
    Exploracao: float


class GrupoDto(BaseModel):
    id: UUID
    nome: str
    labirintos_concluidos: Optional[List[int]]


class CriarGrupoDto(BaseModel):
    nome: str


# Websocket manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


# Create the database and tables
engine = create_engine('sqlite:///./db.sqlite3', echo=True)
Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()


@app.post("/grupo")
async def registrar_grupo(grupo: CriarGrupoDto):
    db = next(get_db())
    grupo_db = Grupo(id=uuid.uuid4(), nome=grupo.nome)
    db.add(grupo_db)
    db.commit()
    grupo_dto = GrupoDto(id=grupo_db.id, nome=grupo_db.nome, labirintos_concluidos=[])
    return {"GrupoId": grupo_dto.id}


@app.post("/labirinto")
async def criar_labirinto(labirinto: LabirintoModel):
    db = next(get_db())
    labirinto_db = Labirinto(entrada=labirinto.entrada, dificuldade=labirinto.dificuldade)
    db.add(labirinto_db)
    db.commit()
    db.refresh(labirinto_db)

    for vertice in labirinto.vertices:
        vertice_db = Vertice(
            id=vertice.id,
            labirinto_id=labirinto_db.id,
            tipo=vertice.tipo
        )
        db.add(vertice_db)
    for aresta in labirinto.arestas:
        aresta_db = Aresta(
            vertice_origem_id=aresta.origemId,
            vertice_destino_id=aresta.destinoId,
            peso=aresta.peso
        )
        db.add(aresta_db)

    db.commit()
    db.refresh(vertice_db)

    return {"LabirintoId": labirinto_db.id}


@app.get("/grupos")
async def retorna_grupos():
    db = next(get_db())
    grupos = db.query(Grupo).all()
    grupos_dto = [GrupoDto(id=grupo.id, nome=grupo.nome, labirintos_concluidos=[]) for grupo in grupos]
    return {"Grupos": grupos_dto}


@app.get("/iniciar/{grupo_id}")
async def iniciar_desafio(grupo_id: UUID):
    db = next(get_db())
    grupo_db = db.query(Grupo).filter(Grupo.id == grupo_id).first()
    if not grupo_db:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    pass


@app.get("/labirintos/{grupo_id}")
async def get_labirintos(grupo_id: UUID):
    db = next(get_db())
    grupo = db.query(Grupo).filter(Grupo.id == grupo_id).first()
    labirintos = db.query(Labirinto).all()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")

    labirintos_dto = [LabirintoDto(LabirintoId=labirinto.id, Dificuldade=labirinto.dificuldade) for labirinto in
                      labirintos]

    return {"Labirintos": labirintos_dto}


@app.get("/sessoes")
async def get_websocket_sessions():
    pass


manager = ConnectionManager()


@app.websocket("/ws/{grupo_id}/{labirinto_id}")
async def websocket_endpoint(websocket: WebSocket, grupo_id: UUID, labirinto_id: int):
    await manager.connect(websocket)
    db = next(get_db())

    try:
        # Obtém o labirinto e seu vértice de entrada
        labirinto = db.query(Labirinto).filter(Labirinto.id == labirinto_id).first()
        if not labirinto:
            await websocket.send_text("Labirinto não encontrado.")
            await manager.disconnect(websocket)
            return

        # Obtém o vértice de entrada
        vertice_atual = db.query(Vertice).filter(Vertice.labirinto_id == labirinto_id,
                                                 Vertice.id == labirinto.entrada).first()

        if not vertice_atual:
            await manager.send_message("Vértice de entrada não encontrado.", websocket)
            await manager.disconnect(websocket)
            return

        # Envia o vértice de entrada para o cliente
        await manager.send_message(
            f"Vértice atual: {vertice_atual.id}, Adjacentes: {vertice_atual.adjacentes.split(',')}", websocket)

        # Loop para interações do cliente
        while True:
            try:
                # Espera por uma mensagem do cliente com timeout de 60 segundos
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)

                if data.startswith("ir:"):
                    # Extrai o id do vértice desejado
                    try:
                        vertice_desejado_id = int(data.split(":")[1].strip())
                    except ValueError:
                        await manager.send_message("Comando inválido. Use 'ir: id_do_vertice'", websocket)
                        continue

                    # Verifica se o vértice desejado está nos adjacentes do vértice atual
                    adjacentes = list(map(int, vertice_atual.adjacentes.split(",")))
                    if vertice_desejado_id not in adjacentes:
                        await manager.send_message("Vértice inválido.", websocket)
                        continue

                    # Move para o vértice desejado
                    vertice_atual = db.query(Vertice).filter(Vertice.labirinto_id == labirinto_id,
                                                             Vertice.id == vertice_desejado_id).first()

                    if not vertice_atual:
                        await manager.send_message("Erro ao acessar o vértice desejado.", websocket)
                        continue

                    # Envia as informações do novo vértice ao cliente
                    await manager.send_message(
                        f"Vértice atual: {vertice_atual.id}, Adjacentes: {vertice_atual.adjacentes.split(',')}",
                        websocket)
                else:
                    await manager.send_message("Comando não reconhecido. Use 'ir: id_do_vertice' para se mover.",
                                               websocket)

            except asyncio.TimeoutError:
                # Timeout de 60 segundos sem mensagem, desconecta o WebSocket
                await manager.send_message("Conexão encerrada por inatividade.", websocket)
                await manager.disconnect(websocket)
                break

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(f"Grupo {grupo_id} desconectado.")


@app.post("/generate-websocket/")
async def generate_websocket_link(grupo_id: UUID, labirinto_id: int):
    db = next(get_db())
    grupo = db.query(Grupo).filter(Grupo.id == grupo_id).first()
    labirinto = db.query(Labirinto).filter(Labirinto.id == labirinto_id).first()

    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    if not labirinto:
        raise HTTPException(status_code=404, detail="Labirinto não encontrado")

    ws_url = f"ws://localhost:8000/ws/{grupo_id}/{labirinto_id}"

    # Salva a sessão no banco de dados
    sessao_ws = SessaoWebSocket(grupo_id=str(grupo_id), conexao=ws_url)
    db.add(sessao_ws)
    db.commit()

    return {"websocket_url": ws_url}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
