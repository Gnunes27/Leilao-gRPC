# Leilao BSI — gRPC + painel web

Projeto didatico para uma apresentacao de Sistemas Distribuidos.

- Participantes enviam lances pelo terminal usando gRPC.
- O navegador exibe o estado do leilao em uma pagina web.
- O servidor controla os lances e aplica as regras.
- O painel atualiza automaticamente a cada 1,2 segundo.

## Estrutura

```text
leilao-grpc/
├── client.py
├── server.py
├── iniciar_cliente.sh
├── iniciar_servidor.sh
├── requirements.txt
├── proto/
│   └── leilao.proto
├── generated/
│   └── __init__.py
├── web/
│   ├── index.html
│   └── images/
└── deploy/
    └── nginx-leilao.conf
```

## Executar localmente

Instale Python 3 e o suporte a ambientes virtuais. Em Ubuntu/Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv
```

No computador servidor:

```bash
chmod +x iniciar_servidor.sh iniciar_cliente.sh
./iniciar_servidor.sh
```

Abra o painel local em `http://127.0.0.1:8080`.

O cliente esta configurado para conectar a `gnunes.abrdns.com:50051`.
Para testar tudo na mesma maquina antes de publicar na AWS, altere temporariamente
a constante `SERVIDOR` em `client.py` para `localhost:50051`.

Em cada computador participante, copie o projeto e execute:

```bash
./iniciar_cliente.sh
```

O cliente solicita apenas o nome do participante. O dominio do servidor ja esta
configurado no codigo.

## Publicar na AWS

### 1. DNS

No provedor DNS que gerencia `gnunes.abrdns.com`, crie/ajuste um registro:

- Tipo: A
- Nome: `gnunes`
- Valor: IPv4 publico (preferencialmente Elastic IP) da instancia EC2

Aguarde a propagacao DNS. O dominio precisa resolver para o IP publico da instancia.

### 2. Security Group da EC2

Adicione regras de entrada:

| Porta | Protocolo | Origem | Uso |
|---|---|---|---|
| 22 | TCP | Seu IP | SSH (restrinja ao seu IP) |
| 80 | TCP | 0.0.0.0/0 | Dashboard web |
| 50051 | TCP | 0.0.0.0/0 | Clientes gRPC |

A porta 8080 nao precisa ficar publica: o Nginx encaminha o trafego localmente.
Nao abra a porta 8080 para a internet.

### 3. Instalar e iniciar o projeto na EC2

Copie o projeto para a instancia. Em Ubuntu:

```bash
sudo apt update
sudo apt install -y python3 python3-venv nginx
chmod +x iniciar_servidor.sh iniciar_cliente.sh
./iniciar_servidor.sh
```

Mantenha o processo do servidor ativo durante a demonstracao. Para uso continuo,
configure-o depois como servico systemd.

### 4. Configurar o Nginx para o dominio

Copie o arquivo de configuracao:

```bash
sudo cp deploy/nginx-leilao.conf /etc/nginx/sites-available/leilao
sudo ln -s /etc/nginx/sites-available/leilao /etc/nginx/sites-enabled/leilao
sudo nginx -t
sudo systemctl reload nginx
```

A pagina ficara disponivel em:

`http://gnunes.abrdns.com`

O Nginx recebe HTTP na porta 80 e encaminha para o painel Python na porta 8080.
Para HTTPS, configure um certificado TLS (por exemplo, com Certbot) antes de
compartilhar o endereco publicamente.

### 5. Clientes

Em cada computador dos participantes:

```bash
./iniciar_cliente.sh
```

Eles informam o nome. O cliente conecta automaticamente a:

`gnunes.abrdns.com:50051`

## Regras implementadas

1. O servidor anuncia quando um participante entra.
2. Um participante nao pode dar dois lances aceitos seguidos.
3. Cada lance aceito precisa ser maior que o lance atual.
4. O painel destaca o maior lance e mostra os lances recentes.

## Adicionar imagem do item depois

Coloque a imagem em `web/images/`, por exemplo:

`web/images/notebook.jpg`

Depois, em `EstadoLeilao.__init__`, no `server.py`, ajuste:

```python
self.item = "Notebook Gamer"
self.imagem = "/images/notebook.jpg"
```

Reinicie o servidor. A pagina carregara a imagem automaticamente.

## Observacoes importantes de seguranca

Esta e uma demonstracao academica. O gRPC usa `insecure_channel` e a porta
50051 fica sem criptografia/autenticacao. Nao utilize este desenho para dados
sensíveis ou um leilao real na internet. Para uma publicacao real, configure
TLS para gRPC (ou um proxy gRPC com TLS), identidade dos participantes,
limites de requisicao e protecao contra abuso.

O painel e somente leitura; toda validacao de lances acontece no servidor.
