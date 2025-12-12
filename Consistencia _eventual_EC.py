import time

class ReplicadorDeDados:
    """Simulação de um servidor de dados com consistência eventual."""
    def __init__(self, nome, atraso_propagacao=0):
        self.nome = nome
        self.dado_local = {"valor": "Inicial", "versao": 0}
        self.atraso_propagacao = atraso_propagacao

    def escrever(self, novo_valor):
        """Atualiza o dado localmente e simula o agendamento da propagação."""
        self.dado_local["valor"] = novo_valor
        self.dado_local["versao"] += 1
        print(f"[{self.nome}] ESCRITA: '{novo_valor}' (Versão {self.dado_local['versao']})")
        # Em um sistema real, aqui ele agendaria o envio para outras réplicas

    def ler(self):
        """Lê o dado localmente."""
        return self.dado_local

    def receber_atualizacao(self, atualizacao):
        """Processa a atualização de outra réplica após um atraso."""
        if atualizacao["versao"] > self.dado_local["versao"]:
            # Simula o tempo de propagação da rede
            time.sleep(self.atraso_propagacao)
            
            self.dado_local = atualizacao
            print(f"[{self.nome}] ATUALIZADO: Recebeu '{self.dado_local['valor']}' (Versão {self.dado_local['versao']})")
        # else: ignora (versão mais antiga)

# --- SIMULAÇÃO ---
print("--- SIMULAÇÃO DE CONSISTÊNCIA EVENTUAL ---")

# Criamos duas réplicas. R2 tem um atraso de propagação de 0.5s
R1 = ReplicadorDeDados("R1")
R2 = ReplicadorDeDados("R2", atraso_propagacao=0.5)

# P1: Escrita em R1
R1.escrever("Mensagem A")
ultima_atualizacao = R1.ler()

# Leitura Imediata (Inconsistência momentânea)
print("\n[Tempo 0]: Leitura Imediata")
print(f"R1 lê: {R1.ler()['valor']}")
print(f"R2 lê: {R2.ler()['valor']}") # R2 ainda vê o valor antigo ("Inicial") -> INCONSISTENTE

# Propagação para R2
print("\n[Tempo 1]: Início da Propagação para R2...")
# Em um sistema real, R1 enviaria a atualização. Aqui, simulamos o recebimento em R2:
R2.receber_atualizacao(ultima_atualizacao)

# Leitura Após Propagação (Consistência Eventual Atingida)
print("\n[Tempo 2]: Leitura após o tempo de propagação de R2 (0.5s)")
print(f"R1 lê: {R1.ler()['valor']}")
print(f"R2 lê: {R2.ler()['valor']}") # R2 já vê o valor novo ("Mensagem A") -> CONSISTENTE