import json
import threading
import time
from concurrent import futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import grpc

from generated import leilao_pb2
from generated import leilao_pb2_grpc


TEMPO_ESPERA_PARTICIPANTES = 5 * 60
TEMPO_LANCE = 15
LANCE_INICIAL_PADRAO = 500


ITENS = [
    {
        "nome": "A Galinha Verde do WhatsApp",
        "imagem": "images/item1.png",
        "lance_inicial": 150.0,
        "descricao": "Ela conversa com vc ou só te responde? Pense bem!."
    },
    {
        "nome": "A Camisa Oficial do Verdao",
        "imagem": "images/item2.png",
        "lance_inicial": 1000.0,
        "descricao": "Vai curintia!"
    },
    {
        "nome": "O Papagaio Dev Senior",
        "imagem": "images/item3.png",
        "lance_inicial": 500.0,
        "descricao": "Este papagaio domina Java, Python e principalmente a arte de dizer 'depende.'"
    },
    {
        "nome": "O Notebook da Xuxa",
        "imagem": "images/item4.png",
        "lance_inicial": 2.50,
        "descricao": "Equipamento tecnologico de ultima geracao, processador de meio nucleo e 0,0002 GHz, 2 Kb de memoria RAM e 1 Mb de armazenamento. Ideal para quem quer se sentir um pouco mais proximo da apresentadora."
    },
    {
        "nome": "O Chinelo de Osama Bin Barack Laden Obama Donald Da Silva Trump",
        "imagem": "images/item5.png",
        "lance_inicial": 0.05,
        "descricao": "Achei no lixo, mas parece que vale algo."
    }
]


class EstadoLeilao:
    """Estado compartilhado entre o servico gRPC e o painel web."""

    def __init__(self):
        self.indice_item = 0
        self.item = ITENS[0]["nome"]
        self.imagem = ITENS[0]["imagem"]
        self.descricao = ITENS[0]["descricao"]
        self.lance_inicial = ITENS[0]["lance_inicial"]
        self.maior_lance = self.lance_inicial
        self.lider = "Leiloeiro"
        self.ultimo_lanceador = None
        self.lances = []
        self.eventos = []
        self.participantes = set()
        self.lock = threading.Lock()

        self.fase = "aguardando_participantes"
        self.prazo_espera = time.monotonic() + TEMPO_ESPERA_PARTICIPANTES
        self.prazo_lance = None

        self.numero_item = 1
        self.vencedor = None
        self.lance_vencedor = None

    def adicionar_evento(self, mensagem, participante=None, valor=None):
        """Adiciona um evento para todos os clientes que acompanham o stream."""
        self.eventos.append(
            leilao_pb2.Atualizacao(
                item=self.item,
                participante=participante or self.lider,
                valor=self.maior_lance if valor is None else valor,
                mensagem=mensagem
            )
        )

    def encerrar_item(self, motivo):
        """Deve ser chamada com self.lock adquirido."""
        if self.fase in ("aguardando_proximo_item", "encerrado"):
            return

        if self.lances:
            self.vencedor = self.lider
            self.lance_vencedor = self.maior_lance
            mensagem = (
                f"FIM DO LEILAO: {self.vencedor} venceu com "
                f"R$ {self.lance_vencedor:.2f}. "
                "Aguardando proximo item."
            )
        else:
            self.vencedor = None
            self.lance_vencedor = None
            mensagem = (
                "O tempo para iniciar/realizar os lances acabou sem vencedor. "
                "Aguardando proximo item. Permaneça conectado!"
            )

        self.fase = "aguardando_proximo_item"
        self.prazo_lance = None
        self.adicionar_evento(mensagem)

        print(f"\n{mensagem}", flush=True)

    def verificar_tempo(self):
        """Monitora os prazos mesmo quando ninguem acessa o painel web."""
        while True:
            time.sleep(0.2)
            with self.lock:
                agora = time.monotonic()

                if (
                    self.fase == "aguardando_participantes"
                    and agora >= self.prazo_espera
                ):
                    self.encerrar_item("tempo de espera esgotado")

                elif (
                    self.fase == "em_andamento"
                    and self.prazo_lance is not None
                    and agora >= self.prazo_lance
                ):
                    self.encerrar_item("tempo para novo lance esgotado")

    def proximo_item(self, nome_item=None):
        """Prepara outro item sem encerrar os streams gRPC dos clientes."""
        with self.lock:
            if self.fase != "aguardando_proximo_item":
                return False, (
                    "O item atual ainda nao terminou. "
                    "Aguarde o cronometro chegar a zero."
                )

            if nome_item:
                # Permite manter o comando manual: proximo Nome personalizado
                self.numero_item += 1
                self.item = nome_item.strip() or f"Item {self.numero_item}"
                self.imagem = ""
                self.descricao = "Item personalizado anunciado pelo leiloeiro."
                self.lance_inicial = LANCE_INICIAL_PADRAO
            else:
                if self.indice_item + 1 >= len(ITENS):
                    return False, "Todos os 5 itens do catalogo ja foram leiloados."
                self.indice_item += 1
                item_catalogo = ITENS[self.indice_item]
                self.numero_item = self.indice_item + 1
                self.item = item_catalogo["nome"]
                self.imagem = item_catalogo["imagem"]
                self.descricao = item_catalogo["descricao"]
                self.lance_inicial = item_catalogo["lance_inicial"]
            self.maior_lance = self.lance_inicial
            self.lider = "Leiloeiro"
            self.ultimo_lanceador = None
            self.lances = []
            self.vencedor = None
            self.lance_vencedor = None
            self.prazo_lance = None

            if self.participantes:
                self.fase = "aguardando_primeiro_lance"
                self.prazo_espera = None
                mensagem = (
                    f"NOVO ITEM: {self.item}. Lance inicial: "
                    f"R$ {self.lance_inicial:.2f}. "
                    "Aguardando o primeiro lance."
                )
            else:
                self.fase = "aguardando_participantes"
                self.prazo_espera = time.monotonic() + TEMPO_ESPERA_PARTICIPANTES
                mensagem = (
                    f"NOVO ITEM: {self.item}. Aguardando participantes "
                    "por 5 minutos."
                )

            self.adicionar_evento(mensagem, participante=self.lider, valor=self.maior_lance)
            print(f"\n{mensagem}", flush=True)
            return True, mensagem

    def snapshot(self):
        with self.lock:
            agora = time.monotonic()

            if self.fase == "aguardando_participantes":
                restante = max(0, int(self.prazo_espera - agora + 0.999))
            elif self.fase == "aguardando_primeiro_lance":
                restante = TEMPO_LANCE
            elif self.fase == "em_andamento":
                restante = max(0, int(self.prazo_lance - agora + 0.999))
            else:
                restante = 0

            descricoes = {
                "aguardando_participantes": "Aguardando participantes",
                "aguardando_primeiro_lance": "Aguardando primeiro lance",
                "em_andamento": "Leilao em andamento",
                "aguardando_proximo_item": "Esperando proximo item",
            }

            return {
                "fase": self.fase,
                "status_leilao": descricoes.get(self.fase, self.fase),
                "tempo_restante": restante,
                "item": self.item,
                "imagem": self.imagem,
                "descricao": self.descricao,
                "numero_item": self.numero_item,
                "total_itens": len(ITENS),
                "lance_inicial": float(self.lance_inicial or 0),
                "maior_lance": float(
                    self.maior_lance
                    if self.maior_lance is not None
                    else self.lance_inicial or 0
                ),
                "lider": self.lider,
                "lances": list(reversed(self.lances[-30:])),
                "participantes": sorted(self.participantes),
                "total_lances": len(self.lances),
                "vencedor": self.vencedor,
                "lance_vencedor": self.lance_vencedor,
            }


class ServidorLeilao(leilao_pb2_grpc.LeilaoServicer):
    def __init__(self, estado):
        self.estado = estado

    def FazerLance(self, request, context):
        nome = request.participante.strip()

        if not nome:
            return leilao_pb2.LanceResponse(
                sucesso=False,
                mensagem="Informe um nome de participante."
            )

        with self.estado.lock:
            if nome not in self.estado.participantes:
                return leilao_pb2.LanceResponse(
                    sucesso=False,
                    mensagem="Entre novamente no leilao para participar."
                )

            if self.estado.fase == "aguardando_proximo_item":
                return leilao_pb2.LanceResponse(
                    sucesso=False,
                    mensagem="Item encerrado. Esperando o servidor iniciar o proximo item."
                )

            if self.estado.fase == "aguardando_participantes":
                return leilao_pb2.LanceResponse(
                    sucesso=False,
                    mensagem="Aguardando participantes."
                )

            if self.estado.fase == "encerrado":
                return leilao_pb2.LanceResponse(
                    sucesso=False,
                    mensagem="O servidor encerrou o leilao."
                )

            if nome == self.estado.ultimo_lanceador:
                return leilao_pb2.LanceResponse(
                    sucesso=False,
                    mensagem=(
                        "Voce acabou de dar um lance. "
                        "Espere outro participante dar um lance valido."
                    )
                )

            if not self.estado.lances and request.valor < self.estado.lance_inicial:
                return leilao_pb2.LanceResponse(
                    sucesso=False,
                    mensagem=(
                        f"O primeiro lance precisa ser de pelo menos "
                        f"R$ {self.estado.lance_inicial:.2f}."
                    )
                )

            if self.estado.lances and request.valor <= self.estado.maior_lance:
                return leilao_pb2.LanceResponse(
                    sucesso=False,
                    mensagem=(
                        f"O lance precisa ser maior que "
                        f"R$ {self.estado.maior_lance:.2f}."
                    )
                )

            self.estado.maior_lance = request.valor
            self.estado.lider = nome
            self.estado.ultimo_lanceador = nome
            self.estado.fase = "em_andamento"
            self.estado.prazo_lance = time.monotonic() + TEMPO_LANCE

            lance = {
                "participante": nome,
                "valor": request.valor,
                "horario": time.strftime("%H:%M:%S"),
            }
            self.estado.lances.append(lance)

            mensagem = f"{nome} deu um lance de R$ {request.valor:.2f}"
            self.estado.adicionar_evento(
                mensagem,
                participante=nome,
                valor=request.valor
            )
            print(mensagem, flush=True)

            return leilao_pb2.LanceResponse(
                sucesso=True,
                mensagem="Lance aceito!"
            )

    def AcompanharLeilao(self, request, context):
        nome = request.participante.strip()
        if not nome:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "O nome do participante e obrigatorio."
            )

        with self.estado.lock:
            proximo_evento = len(self.estado.eventos)
            primeiro_participante = not self.estado.participantes
            self.estado.participantes.add(nome)

            if (
                primeiro_participante
                and self.estado.fase == "aguardando_participantes"
            ):
                self.estado.fase = "aguardando_primeiro_lance"

            mensagem = f"{nome} entrou no leilao!"
            # participante representa o lider atual, nao quem acabou de entrar.
            self.estado.adicionar_evento(
                mensagem,
                participante=self.estado.lider,
                valor=self.estado.maior_lance
            )

        print(mensagem, flush=True)

        # O stream permanece aberto entre itens. So termina quando o cliente
        # fecha a conexao ou o servidor e encerrado.
        while context.is_active():
            evento = None
            with self.estado.lock:
                if proximo_evento < len(self.estado.eventos):
                    evento = self.estado.eventos[proximo_evento]
                    proximo_evento += 1

            if evento is not None:
                yield evento
            else:
                time.sleep(0.2)


class DashboardHandler(BaseHTTPRequestHandler):
    estado = None
    web_dir = Path(__file__).parent / "web"

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/estado":
            payload = json.dumps(
                self.estado.snapshot(),
                ensure_ascii=False
            ).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/" or path == "/index.html":
            arquivo = self.web_dir / "index.html"
        elif path.startswith("/images/"):
            nome = Path(path).name
            arquivo = self.web_dir / "images" / nome
        else:
            self.send_error(404, "Pagina nao encontrada")
            return

        if not arquivo.is_file():
            self.send_error(404, "Arquivo nao encontrado")
            return

        conteudo = arquivo.read_bytes()
        tipo = (
            "text/html; charset=utf-8"
            if arquivo.suffix == ".html"
            else "image/png" if arquivo.suffix.lower() == ".png"
            else "application/octet-stream"
        )

        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(conteudo)))
        self.end_headers()
        self.wfile.write(conteudo)

    def log_message(self, format, *args):
        return


def iniciar_dashboard(estado):
    DashboardHandler.estado = estado
    servidor_web = ThreadingHTTPServer(("0.0.0.0", 8081), DashboardHandler)
    thread = threading.Thread(target=servidor_web.serve_forever, daemon=True)
    thread.start()
    print("Dashboard iniciado na porta 8081.", flush=True)
    return servidor_web


def console_servidor(estado, servidor_grpc):
    print("\nComandos do servidor: 'proximo [nome do item]' ou 'sair'.", flush=True)
    while True:
        try:
            comando = input("Servidor> ").strip()
        except EOFError:
            return

        if not comando:
            continue

        if comando.lower() == "sair":
            servidor_grpc.stop(0)
            return

        if comando.lower() == "proximo" or comando.lower().startswith("proximo "):
            nome_item = comando[7:].strip() if len(comando) > 7 else None
            sucesso, mensagem = estado.proximo_item(nome_item)
            print(mensagem if not sucesso else "Proximo item iniciado.", flush=True)
        else:
            print("Comando desconhecido. Use 'proximo' ou 'sair'.", flush=True)


def iniciar_servidor():
    estado = EstadoLeilao()

    servidor_grpc = grpc.server(
        futures.ThreadPoolExecutor(max_workers=50)
    )
    leilao_pb2_grpc.add_LeilaoServicer_to_server(
        ServidorLeilao(estado),
        servidor_grpc
    )

    servidor_grpc.add_insecure_port("0.0.0.0:50051")
    servidor_grpc.start()
    servidor_web = iniciar_dashboard(estado)

    threading.Thread(
        target=estado.verificar_tempo,
        daemon=True
    ).start()

    threading.Thread(
        target=console_servidor,
        args=(estado, servidor_grpc),
        daemon=True
    ).start()

    print("======================================")
    print("              LEILAO BSI")
    print("======================================")
    print("gRPC:      0.0.0.0:50051")
    print("Dashboard: http://127.0.0.1:8081")
    print(f"Tempo para lance: {TEMPO_LANCE} segundos")
    print("======================================")

    try:
        servidor_grpc.wait_for_termination()
    except KeyboardInterrupt:
        print("\nEncerrando servidores...")
    finally:
        servidor_web.shutdown()
        servidor_grpc.stop(0)


if __name__ == "__main__":
    iniciar_servidor()
