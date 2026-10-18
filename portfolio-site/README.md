# Site do Portfólio Técnico — `portfolio-site/`

Aplicação estática responsiva (HTML5 + CSS3 + JavaScript ES6 Vanilla, zero dependências de build) projetada para publicação direta no **GitHub Pages** (`https://pedroedus.github.io/portifolio/`) ou execução local imediata.

---

## 1. Estrutura da Aplicação

```text
portfolio-site/
├── .nojekyll                  # Desativa processamento Jekyll no GitHub Pages
├── index.html                 # Página principal (Hero, 6 Cases, Simuladores, Matriz Stack, Trajetória e Contato)
├── README.md                  # Instruções de execução e deploy
└── assets/
    ├── css/
    │   └── styles.css         # Design System técnico (Dark/Light mode responsivo)
    ├── js/
    │   └── app.js             # Filtros, Modal de Arquitetura (8 seções) e 3 Motores de Simulação Interativa
    └── data/
        └── projects.json      # Catálogo estruturado de projetos, métricas comprovadas e stack
```

---

## 2. Destaques Funcionais

1. **Posicionamento Técnico Evidenciado:**
   - **1º Data Engineer** · **2º Analytics Engineer** · **3º BI Engineer & Data Apps Specialist**.
   - Banner permanente de governança e confidencialidade explicando que os projetos referem-se às experiências reais em **duas incorporadoras imobiliárias (empresa A e empresa B)**, enquanto 100% dos códigos e bases do repositório utilizam **dados sintéticos (`seed=42`)** para demonstrar o método de engenharia sem expor ativos corporativos.
2. **Galeria Interativa de Estudos de Caso (6 Projetos):**
   - Filtro instantâneo por competência (`Data Warehousing & Snapshots`, `Data Engineering`, `Analytics Engineering`, `Cloud & APIs`, `Reverse Engineering & Governance`, `State Machines & Algorithms`).
   - Destaque visual e arquitetural para o **Case 03 — DW Financeiro (`wh_dw_financeiro`: Motor de Snapshots Semanais/Diários e Diff Engine `mudanca_parcela`)**.
   - Modal de inspeção profunda com as **8 seções obrigatórias** de cada estudo de caso e comandos prontos para rodar a demonstração (`run_demo.py`) e os testes (`pytest`).
3. **3 Simuladores Interativos Ao Vivo no Navegador:**
   - **Simulador 01 (DW Financeiro — Snapshots & Diff Engine):** Permite simular reexecuções idempotentes na mesma `data_snapshot` (atualizando `dt_carga` sem duplicar a partição), injetar aditivos de valor e prorrogações *in-place* no ERP e inspecionar em tempo real a tabela `snap.mudanca_parcela` e a preservação de fornecedores sem órfãos (`dim.fornecedor`).
   - **Simulador 02 (Lakehouse Recebíveis — Gate Staging-First & Roll-Rate):** Permite testar o bloqueio automático quando a cobertura do cálculo noturno cai abaixo de `99,5%`, a regra de exceção do Dia 1 (`aceitar_calc_defasada`) e a matriz de transição $M \to M+1$ com isolamento de cessões (`TipoMnt = 2`).
   - **Simulador 03 (Conciliação Bancária — Pares Transitórios & Detecção In-Place):** Demonstra o expurgo seletivo de pares casados `(Tipo 5, Tipo 6)` na natureza `'0071'` preservando casos unilaterais e a descoberta de validações manuais *in-place* no Snapshot 1.

---

## 3. Como Visualizar Localmente

Você pode abrir o arquivo `index.html` diretamente no navegador (o script possui fallback embutido para protocolo `file://`) ou subir um servidor HTTP local:

```bash
cd portfolio-workspace/portfolio-site
python -m http.server 8080
```

Em seguida, acesse `http://localhost:8080`.

---

## 4. Como Atualizar Dados de Contato (Telefone, E-mail, LinkedIn)

Para atualizar telefone, e-mail ou LinkedIn antes do deploy público:
1. Edite o bloco `CONFIG` no topo de `assets/js/app.js` e a seção `<footer id="contato">` em `index.html`.
2. Opcionalmente, atualize também o bloco `"contacts"` em `assets/data/projects.json`.
