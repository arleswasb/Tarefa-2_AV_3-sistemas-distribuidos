

# Implementação de Modelos de Consistência Distribuída (Twitter)

Este repositório contém o código de implementação da **Tarefa V2 - Parte 2 de Sistemas Distribuídos**, focado na comparação prática entre os modelos de **Consistência Eventual (EC)** e **Consistência Causal (CC)**.

O projeto utiliza um sistema simulado de rede social (Twitter simplificado) para demonstrar como a latência de rede afeta a ordenação e a visibilidade dos dados, especificamente o problema da **Reply Órfã**.

## Objetivo Principal

Demonstrar que:

1.  A **Consistência Eventual (EC)** permite violações causais momentâneas, resultando em *Replies Órfãs* (respostas a posts ainda desconhecidos).
2.  A **Consistência Causal (CC)**, utilizando **Relógios Lógicos Vetoriais (VLC)** e um **Buffer de Mensagens**, previne a *Reply Órfã* ao adiar a entrega de mensagens que violam a ordem causal.

## Tecnologias Utilizadas

* **Linguagem:** Python 3.x
* **Framework Web:** FastAPI (utilizado para criar os endpoints de comunicação entre as réplicas: `/post` e `/share`)
* **Servidor:** Uvicorn (servidor ASGI)
* **Comunicação:** HTTP via biblioteca `requests` (simulação de propagação assíncrona)
* **Controle de Versão:** Git / GitHub

## Configuração e Instalação

### Pré-requisitos

Certifique-se de ter o Python 3.x instalado em seu sistema.

### 1. Clonar o Repositório

```bash
git clone [https://github.com/arleswasb/Tarefa-2_AV_3-sistemas-distribuidos.git](https://github.com/arleswasb/Tarefa-2_AV_3-sistemas-distribuidos.git)
cd Tarefa-2_AV_3-sistemas-distribuidos
````

### 2\. Criar e Ativar o Ambiente Virtual

Recomenda-se o uso de um ambiente virtual (`venv`) para isolar as dependências.

```bash
# Cria o ambiente virtual
python3 -m venv venv

# Ativação (Linux/macOS)
source venv/bin/activate
# Ativação (Windows CMD)
# venv\Scripts\activate.bat
```

### 3\. Instalar Dependências

Instale as bibliotecas necessárias listadas no `requirements.txt`:

```bash
pip install -r requirements.txt
```

*(Ou, alternativamente: `pip install fastapi uvicorn requests pydantic`)*

## Execução do Sistema (3 Réplicas)

O projeto é executado em três terminais separados, onde cada nó recebe um ID (0, 1 ou 2) e o modelo de consistência desejado (`EC` ou `CC`).

### Inicialização dos Nós

Abra três terminais com o `venv` ativado e execute:

| Processo | ID | Modelo | Comando de Inicialização |
| :--- | :--- | :--- | :--- |
| **P0** | 0 | `EC` ou `CC` | `python Unificado_EC_CC.py 0 [EC ou CC]` |
| **P1** | 1 | `EC` ou `CC` | `python Unificado_EC_CC.py 1 [EC ou CC]` |
| **P2** | 2 | `EC` ou `CC` | `python Unificado_EC_CC.py 2 [EC ou CC]` |

-----

## Cenários de Teste

Para demonstrar a diferença entre os modelos, o código `Unificado_EC_CC.py` possui uma lógica de atraso forçado: Se **P0** envia uma mensagem para **P2**, o envio é atrasado em 60 segundos (`time.sleep(60)`).

### Cenário 1: Consistência Eventual (EC)

**Objetivo:** Causar e visualizar a **Reply Órfã**.

| Ação | Emissor | Nó Recebedor | Efeito Esperado (P2) |
| :--- | :--- | :--- | :--- |
| **1. Envio do Post Pai (A)** | P0 (Atraso 30s para P2) | `http://localhost:8080/post` | P2 não recebe A imediatamente. |
| **2. Envio do Reply Filho (R)** | P1 (Viu A) | `http://localhost:8081/post` | **INCONSISTÊNCIA:** P2 recebe R, não encontra A, e o publica com a tag `[ÓRFÃ]`. |
| **3. Chegada do Atrasado** | P0 (Após 60s) | P2 | **CONVERGÊNCIA:** P2 recebe A, associa R e remove a tag `[ÓRFÃ]`. |

**Comandos de Teste (Exemplo no Terminal 4):**

```bash
# 1. Post Pai A
curl -X POST http://localhost:8080/post -H "Content-Type: application/json" -d '{
    "processId": 0,
    "evtId": "A1",
    "author": "Alice",
    "text": "Post Pai Original: A Terra é plana"
}'

# 2. Reply Filho R (Após P1 receber A, geralmente instantâneo)
curl -X POST http://localhost:8081/post -H "Content-Type: application/json" -d '{
    "processId": 1,
    "evtId": "R2",
    "parentEvtId": "A1", 
    "author": "Bob",
    "text": "Reply Filho: Discordo, é um geóide!"
}'
```

### Cenário 2: Consistência Causal (CC)

**Objetivo:** Prevenir a Reply Órfã usando **VLC** e **Buffer**.

| Ação | Emissor | Nó Recebedor | Efeito Esperado (P2) |
| :--- | :--- | :--- | :--- |
| **1. Envio do Post Pai (A)** | P0 (Atraso 30s para P2) | `http://localhost:8080/post` | P2 não recebe A imediatamente. |
| **2. Envio do Reply Filho (R)** | P1 (Viu A) | `http://localhost:8081/post` | **DETECÇÃO:** P2 recebe R. O VLC de R (`[1, 1, 0]`) é incoerente com o VLC local de P2 (`[0, 0, 0]`). A mensagem R é **ADIADA** no `message_buffer` e o usuário **não vê** a Reply. |
| **3. Chegada do Atrasado** | P0 (Após 60s) | P2 | **ENTREGA COERENTE:** P2 recebe A, atualiza o VLC. O `checkBuffer` é acionado e R é **entregue e anexado** imediatamente após A. |

-----

##  Estruturas Chave do Código

### Relógio Lógico Vetorial (VLC)

O estado `vector_clock` é uma lista de inteiros, onde `vector_clock[i]` representa a contagem de eventos que o nó atual viu do nó $P_i$.

### Lógica Causal (Função `isCausallyReady`)

Esta função verifica se uma mensagem recebida (`V_rcv`) pode ser entregue em relação ao Relógio Vetorial local (`V_loc`). A entrega só ocorre se as seguintes condições forem satisfeitas:

* **1. Coerência do Emissor (Não Pulou Eventos):**
    * O componente do emissor $i$ no vetor recebido deve ser exatamente um a mais que o local.
    * **Notação:** `V_rcv[i] = V_loc[i] + 1`

* **2. Coerência dos Outros Processos (Viu todas as Causas):**
    * O componente de qualquer outro processo $j$ no vetor recebido deve ser menor ou igual ao que o nó local já viu.
    * **Notação:** `V_rcv[j] <= V_loc[j]` (Para todo $j \ne i$)


### Buffer de Mensagens

Em Consistência Causal (CC), o `message_buffer` armazena os objetos `Event` que violaram a causalidade (ou seja, falharam na checagem `isCausallyReady`). A função `checkBuffer` é invocada após cada entrega bem-sucedida para tentar liberar mensagens represadas que se tornaram coerentes.


## Contribuição

Este projeto foi desenvolvido por Werbert Arles.

