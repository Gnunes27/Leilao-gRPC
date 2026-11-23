import grpc
import threading
import os

from generated import leilao_pb2
from generated import leilao_pb2_grpc

SERVIDOR = "gnunes.abrdns.com:50051"
terminal_lock = threading.Lock()


def limpar_terminal():
    os.system("cls" if os.name == "nt" else "clear")


def mostrar_cabecalho(nome):
    print("=" * 50)
    print("                  LEILAO BSI")
    print("=" * 50)
    print(f"Participante: {nome}")
    print("Regra: nao sao permitidos dois lances validos seguidos.")
    print("Digite 0 para sair.")
    print("-" * 50)


def acompanhar(stub, nome):
    try:
        atualizacoes = stub.AcompanharLeilao(
            leilao_pb2.Vazio(participante=nome)
        )

        for atualizacao in atualizacoes:
            with terminal_lock:
                print(f"\n[LEILAO] {atualizacao.mensagem}")
                print(
                    f"Item: {atualizacao.item} | "
                    f"Lider: {atualizacao.participante} | "
                    f"Maior lance: R$ {atualizacao.valor:.2f}"
                )
                print("----------------------------------------------")

    except grpc.RpcError as erro:
        with terminal_lock:
            print("\nConexao encerrada:", erro.details())


def iniciar_cliente():
    nome = input("Seu nome: ").strip()
    if not nome:
        print("O nome e obrigatorio.")
        return

    canal = grpc.insecure_channel(SERVIDOR)
    stub = leilao_pb2_grpc.LeilaoStub(canal)

    try:
        print(f"Conectando a {SERVIDOR}...")
        grpc.channel_ready_future(canal).result(timeout=12)

        thread = threading.Thread(
            target=acompanhar,
            args=(stub, nome),
            daemon=True
        )
        thread.start()

        with terminal_lock:
            limpar_terminal()
            mostrar_cabecalho(nome)

        while True:
            try:
                with terminal_lock:
                    entrada = input("Digite seu lance: R$ ").strip()
                valor = float(entrada.replace(",", "."))
            except ValueError:
                with terminal_lock:
                    print("Digite um valor numerico valido.")
                continue

            if valor == 0:
                break

            resposta = stub.FazerLance(
                leilao_pb2.LanceRequest(
                    participante=nome,
                    valor=valor
                ),
                timeout=8
            )

            with terminal_lock:
                if resposta.sucesso:
                    limpar_terminal()
                    mostrar_cabecalho(nome)
                    print(f"\n[{nome}] Lance aceito!")
                   
                    print()
                else:
                    print(resposta.mensagem)

    except grpc.FutureTimeoutError:
        print("Nao foi possivel conectar ao servidor.")
        print("Verifique sua internet, o dominio e a porta 50051.")
    except grpc.RpcError as erro:
        print("Erro na comunicacao:", erro.details())
    except KeyboardInterrupt:
        print("\nSaindo do leilao...")
    finally:
        canal.close()


if __name__ == "__main__":
    iniciar_cliente()
