import sys
import uvicorn
import threading
import time
import requests
import uuid
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict
from collections import defaultdict

app = FastAPI()

# ------------------------------------------------------------
# ESTADO GLOBAL E CONFIGURAÇÃO
# ------------------------------------------------------------

# FLAG: Define o modelo de consistência (pode ser 'EC' ou 'CC')
CONSISTENCY_MODEL = 'EC' 

NUM_PROCESSOS = 3
myProcessId = 0                # id da réplica atual (definido via argv)
vector_clock = [0] * NUM_PROCESSOS # Usado apenas em CC
posts = defaultdict(list)
replies = defaultdict(list)
message_buffer = []          # Buffer para mensagens adiadas (apenas em CC)

processes = [
    "http://localhost:8080",
    "http://localhost:8081",
    "http://localhost:8082",
]

# ------------------------------------------------------------
# MODELO DE EVENTO
# ------------------------------------------------------------
class Event(BaseModel):
    processId: int
    evtId: str
    parentEvtId: Optional[str] = None
    author: str
    text: str
    # O VLC (Vector Logical Clock) é usado para rastrear causalidade
    vectorClock: Optional[List[int]] = None 
    
# ------------------------------------------------------------
# FUNÇÕES AUXILIARES DE REDE E THREADING
# ------------------------------------------------------------

def async_send(url: str, payload: dict, delay_s: int = 0):
    """
    Envia o payload para a URL de destino em uma thread separada,
    com um atraso opcional.
    """
    def worker():
        try:
            if delay_s > 0:
                print(f"    [P{myProcessId}][{CONSISTENCY_MODEL}] -> ATRAZO de {delay_s}s para {url}")
                time.sleep(delay_s) # <--- Atraso introduzido aqui!
                
            requests.post(url, json=payload, timeout=5) # Aumentei o timeout para dar tempo
            print(f"    [P{myProcessId}][{CONSISTENCY_MODEL}] -> Evento enviado para {url}")
            
        except requests.exceptions.RequestException as e:
            print(f"    [P{myProcessId}] ERRO ao enviar para {url}: {e}")

    threading.Thread(target=worker).start()
    
# ------------------------------------------------------------
# LÓGICA DE CONSISTÊNCIA CAUSAL (CC)
# ------------------------------------------------------------

def isCausallyReady(vc_recebido: List[int], id_emissor: int) -> bool:
    """
    Verifica se a mensagem pode ser entregue com base no VLC.
    """
    global vector_clock
    
    # 1. Checa se não pulou o último evento do emissor
    if vc_recebido[id_emissor] != vector_clock[id_emissor] + 1:
        return False

    # 2. Checa se vimos tudo que o emissor viu dos outros
    for i in range(NUM_PROCESSOS):
        if i != id_emissor and vc_recebido[i] > vector_clock[i]:
            return False 
            
    return True

def checkBuffer():
    """
    Tenta liberar as mensagens adiadas no buffer.
    """
    global message_buffer
    
    if not message_buffer:
        return

    remaining_buffer = []
    delivered_in_this_pass = False

    for event in message_buffer:
        vc_recebido = event.vectorClock
        id_emissor = event.processId
        
        if vc_recebido and isCausallyReady(vc_recebido, id_emissor):
            # Causalmente pronta! Entregar e marcar para remover
            _deliverAndApply(event)
            delivered_in_this_pass = True
        else:
            # Não está pronta, mantém no buffer
            remaining_buffer.append(event)
            
    message_buffer = remaining_buffer
    
    if delivered_in_this_pass and message_buffer:
        # Se entregamos algo, isso pode ter liberado outras mensagens (entrega encadeada)
        checkBuffer() 
        
# ------------------------------------------------------------
# LÓGICA DE APLICAÇÃO (Comum a EC e CC)
# ------------------------------------------------------------

def _deliverAndApply(msg: Event):
    """
    Função interna que aplica o evento ao estado da aplicação e atualiza o VLC (se CC).
    """
    global vector_clock, posts, replies, myProcessId
    
    # Se CC, faz o merge do VLC
    if CONSISTENCY_MODEL == 'CC' and msg.vectorClock:
        vc_recebido = msg.vectorClock
        # Atualiza o VLC (max entre local e recebido)
        for i in range(NUM_PROCESSOS):
            vector_clock[i] = max(vector_clock[i], vc_recebido[i])

    # Aplica ao estado do Twitter
    if msg.parentEvtId is None:
        posts[msg.evtId].append(msg)
    else:
        replies[msg.parentEvtId].append(msg)
    
    print(f"\n[{msg.author} P{msg.processId}] ENTREGUE ({CONSISTENCY_MODEL}): '{msg.text[:30]}...' | VLC: {vector_clock}")
    showFeed()


# ------------------------------------------------------------
# FUNÇÃO CENTRAL DE PROCESSAMENTO DE MENSAGENS RECEBIDAS (/share)
# ------------------------------------------------------------

def processMsg(msg: Event):
    """
    Decide se entrega imediatamente, adia ou simplesmente aplica (baseado na FLAG).
    """
    if CONSISTENCY_MODEL == 'EC':
        # Consistência Eventual (EC): Sempre entrega imediatamente, mesmo se for órfã.
        # Isto resultará nas replies órfãs.
        _deliverAndApply(msg)
        
    elif CONSISTENCY_MODEL == 'CC':
        # Consistência Causal (CC): Checa o VLC antes de entregar.
        vc_recebido = msg.vectorClock
        id_emissor = msg.processId

        if vc_recebido is None: # Evento local (já marcado) ou malformado. Trata como entrega.
             _deliverAndApply(msg)
             return
        
        if isCausallyReady(vc_recebido, id_emissor):
            # Causalmente coerente, entrega imediata e tenta liberar o buffer
            _deliverAndApply(msg)
            checkBuffer()
        else:
            # Violação causal detectada, adia a mensagem
            print(f"\n[P{myProcessId}][CC] ADIADA: '{msg.text[:30]}...' VC Rcv {vc_recebido} vs Local {vector_clock}")
            message_buffer.append(msg)
        
# ------------------------------------------------------------
# ENDPOINTS HTTP (O roteamento é o mesmo, só muda a lógica interna)
# ------------------------------------------------------------

@app.post("/post")
def post(msg: Event):
    """
    Endpoint para gerar posts/replies locais.
    """
    global vector_clock
    
    # 1. Lógica de atualização local (permanece a mesma)
    if msg.processId == myProcessId:
        vector_clock[myProcessId] += 1
        msg.vectorClock = vector_clock[:] 
    
    _deliverAndApply(msg)

    # 2. Reencaminhamento e Aplicação de Atraso SELETIVO
    payload = msg.model_dump()
    
    for i, url in enumerate(processes):
        if i != myProcessId:
            
            # Condição para o Teste Específico (Se P0 estiver enviando a mensagem Pai)
            delay = 0
            if myProcessId == 0 and i == 2: 
                delay = 30 
            
            async_send(url + "/share", payload, delay)

    return {"status": "ok", "evtId": msg.evtId, "vectorClock": vector_clock}


@app.post("/share")
def share(msg: Event):
    """
    Endpoint para receber eventos de outras réplicas.
    """
    processMsg(msg)
    return {"status": "ok", "evtId": msg.evtId}

# ------------------------------------------------------------
# APRESENTAÇÃO / DEBUG
# ------------------------------------------------------------

def showFeed():
    """
    Exibe o feed. Em EC, procurará por órfãs. Em CC, não deve encontrar.
    """
    print(f"\n--- FEED (P{myProcessId} | Modelo: {CONSISTENCY_MODEL} | Buffer: {len(message_buffer)} | VLC: {vector_clock}) ---")
    
    post_ids_conhecidos = set(posts.keys())
    tem_orfas = False

    # Exibe posts e replies
    for post_id, msgs in posts.items():
        if msgs:
            post = msgs[0]
            vc_str = f"VLC: {post.vectorClock}" if post.vectorClock else "N/A"
            print(f"[{vc_str}] POST ({post.author}): {post.text} (ID: {post.evtId[:4]})")
            
            if post_id in replies:
                for reply in replies[post_id]:
                    rpl_vc_str = f"VLC: {reply.vectorClock}" if reply.vectorClock else "N/A"
                    print(f"  -> REPLY ({reply.author}): {reply.text} ({rpl_vc_str})")

    # Verifica Replies Órfãs (O foco do teste EC)
    for parent_id, rpl_list in replies.items():
        if parent_id not in post_ids_conhecidos:
            if not tem_orfas:
                print("\n*** [EC]: REPLIES ÓRFÃS ENCONTRADAS (INCONSISTÊNCIA) ***")
                tem_orfas = True
            
            for reply in rpl_list:
                print(f"  [ÓRFÃ] REPLY ({reply.author}): {reply.text} (Pai desconhecido: {parent_id[:4]})")
    
    if not posts and not replies and not message_buffer:
        print("Feed vazio.")

# # ------------------------------------------------------------
# INICIALIZAÇÃO DO NÓ (Rodar o servidor)
# ------------------------------------------------------------

if __name__ == "__main__":
    """
    Inicializa a réplica:
    Argumentos esperados: [ProcessID] [Modelo de Consistência ('EC' ou 'CC')]
    Ex: python your_file.py 0 EC
    """
    
    if len(sys.argv) < 3:
        print("ERRO: Forneça o ID do Processo e o Modelo de Consistência como argumentos.")
        print("Uso: python nome_do_arquivo.py <ID do Processo 0-2> <EC ou CC>")
        sys.exit(1)
        
    try:
        myProcessId = int(sys.argv[1])
        if myProcessId < 0 or myProcessId >= NUM_PROCESSOS:
            raise ValueError
    except ValueError:
        print(f"ERRO: ID do Processo deve ser um número entre 0 e {NUM_PROCESSOS-1}.")
        sys.exit(1)
        
    # A PARTIR DAQUI, o Python já sabe que CONSISTENCY_MODEL é global
    
    model_arg = sys.argv[2].upper()
    if model_arg not in ['EC', 'CC']:
        print("ERRO: O Modelo de Consistência deve ser 'EC' ou 'CC'.")
        sys.exit(1)
        
    CONSISTENCY_MODEL = model_arg # Atribuição correta
    
    port = int(processes[myProcessId].split(":")[-1])
    
    print(f"\n--- INICIANDO NÓ P{myProcessId} ({processes[myProcessId]}) ---")
    print(f"--- MODELO DE CONSISTÊNCIA: {CONSISTENCY_MODEL} ---")
    
    # Inicia o servidor Uvicorn (necessário para rodar o FastAPI)
    uvicorn.run(app, host="localhost", port=port)