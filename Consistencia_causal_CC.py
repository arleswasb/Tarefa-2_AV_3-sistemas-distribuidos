NUM_PROCESSOS = 3

class VectorClock:
    """Implementa o Relógio Lógico Vetorial."""
    def __init__(self, id_processo):
        self.id = id_processo
        # O relógio é um vetor [0, 0, 0, ...] com tamanho igual ao número de processos
        self.clock = [0] * NUM_PROCESSOS

    def tick(self):
        """Incrementa o componente próprio do relógio."""
        self.clock[self.id] += 1
        return self.clock

    def merge(self, other_clock):
        """Atualiza o relógio local com o relógio recebido."""
        for i in range(NUM_PROCESSOS):
            self.clock[i] = max(self.clock[i], other_clock[i])

class ProcessoCausal:
    """Simula um nó que aplica a Consistência Causal com VLC."""
    def __init__(self, id_processo, nome):
        self.id = id_processo
        self.nome = nome
        self.vc = VectorClock(id_processo)
        self.estado = {}
        # Buffer para mensagens que violam a causalidade e precisam ser adiadas
        self.buffer = []

    def escrever(self, chave, valor):
        """Executa uma escrita (evento local) e atualiza o VLC."""
        self.vc.tick()
        self.estado[chave] = (valor, self.vc.clock[:]) # Salva o valor e o VLC da escrita
        print(f"[{self.nome} P{self.id}] ESCRITA: {chave}='{valor}'. VLC: {self.vc.clock}")
        # Retorna a mensagem para simular o envio
        return {"chave": chave, "valor": valor, "vc_escrita": self.vc.clock[:]}

    def checar_causalidade(self, vc_recebido):
        """Verifica se a mensagem pode ser entregue (não viola a causalidade)."""
        vc_local = self.vc.clock
        id_emissor = vc_recebido.index(max(vc_recebido)) # Assume que o maior componente é o emissor
        
        # 1. Condição do Próprio Emissor: O emissor incrementou apenas uma vez
        emissor_ok = vc_recebido[id_emissor] == vc_local[id_emissor] + 1
        
        # 2. Condição dos Outros Processos: Vimos tudo que o emissor viu, exceto o novo evento dele
        outros_ok = True
        for i in range(NUM_PROCESSOS):
            if i != id_emissor and vc_recebido[i] > vc_local[i]:
                # Se o VC recebido mostra que outro processo (i) está mais avançado
                # do que o nosso local, significa que perdemos uma atualização de P(i)
                outros_ok = False
                break
        
        return emissor_ok and outros_ok

    def receber_mensagem(self, mensagem):
        """Simula o recebimento e tenta entregar a mensagem de forma causal."""
        vc_recebido = mensagem["vc_escrita"]
        
        if self.checar_causalidade(vc_recebido):
            # Causalmente coerente, entrega imediata
            self.vc.merge(vc_recebido) # Atualiza o relógio local
            self.estado[mensagem["chave"]] = (mensagem["valor"], vc_recebido)
            print(f"[{self.nome} P{self.id}] ENTREGA IMEDIATA de '{mensagem['valor']}'. Novo VLC: {self.vc.clock}")
        else:
            # Violação causal detectada, a mensagem deve ser bufferizada/adiada
            self.buffer.append(mensagem)
            print(f"[{self.nome} P{self.id}] ADIADA: Mensagem '{mensagem['valor']}' violaria a causalidade. VC recebido {vc_recebido} vs local {self.vc.clock}")


# --- CENÁRIO DE TESTE DE CONSISTÊNCIA CAUSAL ---
# Três processos: P0, P1, P2
P0 = ProcessoCausal(0, "Alice")
P1 = ProcessoCausal(1, "Bob")
P2 = ProcessoCausal(2, "Charlie")

# Cenário 1: Escrita Causal
print("\n--- CENÁRIO CAUSALMENTE COERENTE ---")
# 1. P0 escreve A
msg_A = P0.escrever("A") 
P1.vc.merge(msg_A["vc_escrita"]) # Simula P1 lendo A antes de escrever B (dependência causal)

# 2. P1 escreve B (causalmente dependente de A)
msg_B = P1.escrever("B")

# P0 e P2 recebem A e B. P0 já viu A (pois escreveu). P2 deve receber A antes de B

print("\nTentativa de entrega de A:")
P2.receber_mensagem(msg_A)

print("\nTentativa de entrega de B:")
# Se P2 receber B antes de A (ex: se msg_A atrasar e msg_B for mais rápida)
# P2 deve detectar a violação e adiar B, pois B depende de A.
# No nosso código, P2 ainda não fundiu (merge) o relógio de A.
# VC de msg_B: [1, 2, 0]
# VC local de P2: [0, 0, 0]
# O componente P0 (1) não é visto localmente. O componente P1 (2) é um salto de 2.

# NOTA: O código acima é uma SIMPLIFICAÇÃO da lógica de entrega. 
# Em um sistema real, o check é mais complexo e envolve o estado do buffer.
# A função `checar_causalidade` simplificada deve detectar o salto!

# P2 ainda não entregou A (se recebesse A primeiro, seu VC seria [1, 0, 0]).
# Ao receber B (VC: [1, 2, 0]), detecta:
#   - P1 saltou de 0 para 2.
#   - P0 está em 1 (não visto).
# A mensagem B deve ser **ADIADA** por violar a causalidade.
P2.receber_mensagem(msg_B)

# P2 finalmente entrega A (que estava no buffer da rede/chegou agora)
# P2.receber_mensagem(msg_A) 
# Isso permite que P2 processe B do buffer (não implementado, mas é o próximo passo)