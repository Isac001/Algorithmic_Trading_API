# Algorithmic_Trading_API

Esse projeto se trata de uma API REST completa de backtesting para o mercado financeiro, construída no padrão Monolito Modular com FastAPI e orquestração com Docker Compose. Seu núcleo utiliza o framework Backtrader para simular estratégias de Trend Following (como Cruzamento de Médias Móveis e Breakout), incorporando regras rigorosas de gestão de risco que limitam a perda máxima a 1% do capital por trade.

## 💻 Principais Tecnologias e Bibliotecas Utilizadas

O projeto foi construído sobre uma base de software de código aberto robusta, garantindo alta performance, confiabilidade e facilidade de manutenção.

### Arquitetura e Infraestrutura

| Tecnologia | Uso Principal |
| :--- | :--- |
| **Python 3.11** | Linguagem de desenvolvimento principal. |
| **Docker Compose** | Orquestração do ambiente de microsserviços (`trading_api`, `database`, `daily_indicator_worker`). |
| **FastAPI** | Framework da API REST, garantindo velocidade e alta performance. |
| **PostgreSQL** | Banco de dados relacional para persistência de dados e resultados. |
| **SQLAlchemy 2.0** | ORM (Object-Relational Mapper) para interagir com o PostgreSQL e gerenciar o modelo de dados. |
| **Alembic** | Ferramenta de migração de banco de dados para versionamento seguro do esquema. |

### Módulos de Backtesting e Dados

| Biblioteca | Uso Principal |
| :--- | :--- |
| **Backtrader** | Motor principal para a execução de todas as simulações de backtest. |
| **yfinance** | Coleta de dados históricos de mercado (OHLCV) de ações. |
| **Pandas / NumPy** | Manipulação eficiente de séries temporais e cálculo de indicadores técnicos (SMA, ATR). |
| **Pytest** | Framework de testes automatizados para validar a lógica de risco e indicadores. |
| **Pydantic v2** | Validação rigorosa dos contratos de dados (schemas) da API. |

## Contêineres em Execução no Projeto

| Nome do Contêiner          | Serviço Principal               | Propósito no Projeto                                                                 |
|----------------------------|--------------------------------|-------------------------------------------------------------------------------------|
| **trading_api**            | FastAPI Application (app)       | Hospeda a API REST (servidor web). É o ponto de entrada para todas as requisições (Backtest, Listagem, Health Check). |
| **database**               | PostgreSQL                     | Contém o Banco de Dados central. Armazena prices, indicators, trades e todos os resultados do backtest. |
| **daily_indicator_worker** | Rotina Diária (Cron Job)        | Contêiner dedicado a tarefas em background. Executa a rotina `daily_indicators` para atualizar dados e recalcular features. |

Essa orquestração tripartite garante que a sua aplicação seja **reprodutível**, tenha **serviços isolados** e suporte **automação de tarefas de manutenção** (como a rotina diária), que é um diferencial importante do projeto.


## 🛠️ Pré-Requisitos e Guia de Setup

Para garantir a total reprodutibilidade do projeto (Monolito Modular orquestrado por Docker), seu ambiente deve atender aos seguintes pontos.

### 1. Requisitos de Infraestrutura

Seu sistema precisa ter o **Docker** instalado e funcionando para gerenciar o ambiente conteinerizado.

| Ferramenta | Propósito |
| :--- | :--- |
| **Docker Engine** | Executa os contêineres (`trading_api`, `database`, `daily_indicator_worker`). |
| **Docker Compose** | Orquestra os três serviços em uma rede única. |

## 2. Requisitos de Código Local

Para rodar os testes (`pytest`), o script de demonstração (`run_full_demo.py`), e o script de criação de notebooks (`visualize_results.py`) localmente, você precisa do ambiente **Python** configurado. Lembre-se de rodar os comandos na raiz do projeto, a pasta `algorithmic_trading_api`.

| Ferramenta         | Ação Sugerida                                                                 |
|--------------------|-------------------------------------------------------------------------------|
| **Python 3.11**    | Instale a versão 3.11 (o ambiente Docker a utilizará).                        |
| **Ambiente Virtual** | Crie e ative um ambiente virtual: `python3 -m venv venv`                  |
| **Dependências**   | Instale todas as bibliotecas necessárias: `pip install -r requirements.txt`   |


---

### 🔑 Guia de Configuração do Arquivo `.env`

O arquivo `.env` é **CRUCIAL** para que a sua API se conecte ao banco de dados PostgreSQL. Ele deve estar na **raiz do projeto**.

#### Ação: Criar o Arquivo `.env`

Crie um arquivo chamado **`.env`** com o seguinte conteúdo **exato**:

```bash
DATABASE_URL="postgresql://admin:root@db:5432/database"
```

## 🛠️ Como Iniciar o Projeto (End-to-End)

Para inicializar todo o ambiente de trading algorítmico (API REST, Banco de Dados PostgreSQL e Rotina de Atualização Diária), execute na raiz do projeto `algorithmic_trading_api` o comando:

```bash
docker compose up 
```

Utilize o parâmetro `-d` caso não precise acompanhar os logs da aplicação.

### 1. Iniciar e Construir (Primeira Vez)

Este comando constrói a imagem do zero, inicia o PostgreSQL e executa as migrações (Alembic) antes de iniciar a API.

```bash
docker compose up --build
```

Utilize o parâmetro `-d` caso não precise acompanhar os logs da aplicação.

## 🌐 Acesso à API e Documentação (OpenAPI)

Uma vez que o comando `docker compose up --build -d` seja concluído, sua API **FastAPI** estará totalmente operacional no host local.

### Como Acessar e Inspecionar o Projeto

Para obter uma visão completa de todos os endpoints e schemas de dados, acesse a URL da documentação gerada automaticamente pelo FastAPI:

👉 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

Ao acessar esta URL, você terá uma visão da arquitetura modular do projeto:

- **Validação de Infraestrutura**  
  Use `GET /health` para verificar a conexão com o Banco de Dados.

- **Módulo Backtesting**  
  Explore os endpoints:  
  - `POST /backtests/run`  
  - `GET /backtests`  
  - `GET /backtests/{id}/results`

- **Módulo Data Sourcing**  
  Use `POST /data-sourcing/indicators/update` para acionar a rotina de ingestão e adicionar novas ações ao Banco de Dados.


## ✅ Validação e Teste do Projeto (End-to-End)

Após a execução do `docker compose up --build -d` ser concluída, você também será capaz de executar comandos de validação e teste. Estes logo abaixo.

---

### 1. Testes de Qualidade (Pytest)

É de fundamental importância o uso de testes unitários, quando o ambiente docker é buildado já é feito as validações e testes. Para fins de maior depuração sobre esses testes, rode o comando:

```bash
docker compose run --rm app pytest tests/test_strategies_risk.py -v -s
```

### 2. Execução da Demonstração Completa (Fluxo de Dados)

Execute o script de demonstração para rodar toda a cadeia de valor do sistema: **Ingestão de Dados**, **Cálculo de Indicadores** e **Backtests**.

**Ação:** rode este comando na raiz do seu venv local:

```bash
python3 run_full_demo.py
```

Validação: o script irá disparar os backtests e o log final confirmará o status COMPLETED para cada execução.

### 3. Visualização de Resultados

Para gerar o gráfico da **Curva de Equity** e do **Drawdown**, utilize o script de visualização.

**Ação:** após o `run_full_demo.py` ter criado os registros de backtest (`COMPLETED`), execute este comando na raiz do seu venv local:

```bash
python3 visualize_results.py
```

Esse comando exibirá no terminal um menu interativo. A interface só será apresentada corretamente se o comando for executado após a finalização do python3 `run_full_demo.py`.

```bash
=== Trading Algorithmic API - Results Visualization ===

Discovering existing backtest IDs...

Found 4 backtest(s) with results

============================================================
AVAILABLE COMPLETED BACKTESTS
============================================================
ID: 1 | Symbol: PETR4.SA
ID: 2 | Symbol: VALE3.SA
ID: 3 | Symbol: ITUB4.SA
ID: 4 | Symbol: EMBR3.SA

OPTIONS:
1. Enter specific backtest ID
2. View ALL backtests
3. Exit

Select option (1-3): 
```
Com esse menu, você poderá gerar os gráficos de cada backtest listado digitando `1`, pressionando `Enter` e, em seguida, informando o `ID` da ação que deseja visualizar.

## 🛑 Como Desmontar e Limpar o Ambiente Docker

Para encerrar completamente os serviços e garantir que o seu sistema fique limpo, utilize o comando `down` do Docker Compose.  
Este processo garante que as portas sejam liberadas e que os dados temporários sejam removidos.

### 1. Parar e Remover os Serviços

Execute este comando na raiz do seu projeto (onde o `docker-compose.yaml` está):

```bash
docker compose down
```

Resultado: Para os serviços (`trading_api`, `daily_worker`, `database`) e remove os contêineres e redes.

### 2. Limpeza Total (Remover Dados do Banco de Dados)

Se você quiser apagar permanentemente todos os dados de backtest e preços que foram salvos no PostgreSQL, adicione a flag `--volumes` (`-v`):

```bash
docker compose down --volumes
```

⚠️ Atenção: Este comando remove o volume `postgres_data` e todos os seus dados serão perdidos.

# FIM
Espero que esse projeto seja útil para estudos ou testes de quem esteja lendo. Agradeço demais a sua atençao!

By: `Isac Diógenes`