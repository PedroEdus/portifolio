/**
 * Camada em linguagem simples dos 6 projetos (problema -> o que eu fiz -> resultado).
 * Os detalhes técnicos continuam em app.js / projects.json e aparecem no botão
 * "Ver detalhes técnicos".
 */

const REPO_CASES_URL = "https://github.com/PedroEdus/portifolio/tree/main/case-studies/";

// Ordem de exibição: do resultado mais fácil de entender para o mais técnico.
const PLAIN_ORDER = [
  "projeto-02-conciliacao-bancaria",
  "projeto-03-dw-snapshots-diff",
  "projeto-01-lakehouse-recebiveis",
  "projeto-04-marketing-crm-cloud",
  "projeto-06-maquina-estados-imobiliario",
  "projeto-05-engenharia-reversa-bi"
];

const PLAIN_CONTENT = {
  "projeto-02-conciliacao-bancaria": {
    area: "Financeiro",
    title: "Conciliação bancária: de 26 dias para 3",
    problem: "Todo fechamento semanal exigia cruzar o extrato dos bancos com milhares de lançamentos internos. Lançamentos de passagem atrapalhavam a leitura e correções feitas à mão escondiam o tempo real gasto. O fechamento chegava a levar 26 dias.",
    solution: "Refiz o cálculo do saldo de cada conta a partir das fontes do sistema e comparei com a tela oficial: bateu em todas as contas e dias. Criei uma regra que retira os lançamentos de passagem sem esconder os erros de verdade e uma checagem que mostra quanto tempo cada conciliação realmente levou.",
    results: [
      "Fechamento semanal caiu de 26 para 3 dias",
      "Saldo conferido em 6.330 de 6.330 combinações de conta e dia, sem diferença",
      "Mais de 13 mil linhas de ruído removidas automaticamente"
    ],
    tools: ["Microsoft Fabric", "PySpark", "SQL", "Python"]
  },
  "projeto-03-dw-snapshots-diff": {
    area: "Financeiro",
    title: "Contas a pagar com memória: o que mudou desde a semana passada?",
    problem: "No sistema de gestão, quando uma parcela muda de valor, de vencimento ou de centro de custo, a informação antiga é apagada. A diretoria não conseguia responder à pergunta mais simples: o que mudou na carteira de pagamentos entre a semana passada e hoje?",
    solution: "Criei um banco de dados analítico que tira uma foto semanal do contas a pagar (cerca de 2,6 milhões de linhas por foto) e compara fotos consecutivas, apontando cada parcela que mudou de valor, vencimento ou classificação. Se uma carga precisa rodar de novo, nada é duplicado.",
    results: [
      "Auditoria do que mudou na carteira, semana a semana",
      "Carga completa em cerca de 12 minutos",
      "5.309 alterações diárias identificadas e explicadas, parcela por parcela"
    ],
    tools: ["Microsoft Fabric", "SQL", "Power BI"],
    featured: true,
    simulatorHint: true
  },
  "projeto-01-lakehouse-recebiveis": {
    area: "Cobrança",
    title: "Painel de inadimplência em que dá para confiar",
    problem: "Os números de cobrança vinham de arquivos antigos e difíceis de auditar. Cessões de crédito se misturavam com cancelamentos, custas jurídicas com parcelas e, quando o cálculo noturno do sistema atrasava, os relatórios saíam errados sem ninguém perceber.",
    solution: "Montei a estrutura de dados em camadas no Microsoft Fabric, com um portão de segurança: se os dados da noite chegam incompletos, a atualização é bloqueada e o painel continua mostrando o último número correto. Também separei cessões de cancelamentos de verdade e criei a visão de como os atrasos evoluem de um mês para o outro.",
    results: [
      "Números conferidos célula a célula entre duas implementações independentes",
      "Resultados batendo com os relatórios antigos, cidade a cidade",
      "Fim das divergências entre os relatórios financeiros e os comerciais"
    ],
    tools: ["Microsoft Fabric", "PySpark", "SQL", "Power BI"]
  },
  "projeto-04-marketing-crm-cloud": {
    area: "Marketing e vendas",
    title: "Todo o marketing e as vendas em um só painel",
    problem: "O investimento em anúncios estava espalhado em várias plataformas (Google Ads, Meta, Google Analytics, entre outras), sem um padrão de nomes entre as campanhas e as vendas. Ninguém enxergava o resultado completo por cidade e por empreendimento.",
    solution: "Criei rotinas automáticas que buscam os dados das plataformas todos os dias e guardam tudo no BigQuery. Elas continuam corretas mesmo se uma plataforma falhar no meio da carga ou reajustar números do passado. Também criei a leitura automática dos nomes das campanhas (cidade, estado, lançamento) e um aplicativo web para a diretoria.",
    results: [
      "Plataformas reunidas e atualizadas automaticamente",
      "Aplicativo executivo bem mais leve e rápido",
      "Clientes elegíveis resgatados após a compensação bancária, com auditoria",
      "Rotinas rodando sem pagar servidor para orquestrá-las"
    ],
    tools: ["Python", "BigQuery", "GitHub Actions", "Streamlit"]
  },
  "projeto-06-maquina-estados-imobiliario": {
    area: "Comercial",
    title: "Máquina do tempo do estoque de imóveis",
    problem: "Para entender a velocidade de vendas era preciso saber a situação exata de cada unidade em cada mês do passado. Mas os dados vinham de um sistema de gestão e de vários CRMs diferentes, com contradições, como um cancelamento registrado meses depois de a unidade já ter sido vendida de novo.",
    solution: "Criei uma regra de linha do tempo que resolve essas contradições e reconstrói o estoque mês a mês, sem unidade com duas situações ao mesmo tempo. Também limpei erros de digitação nos preços por metro quadrado, corrigindo pela inflação da construção (INCC), e distribuí os compradores no mapa sem que os pontos se sobreponham.",
    results: [
      "Histórico mensal de estoque reconstruído, mês a mês",
      "Cada unidade com uma única situação por mês",
      "Curvas de preço por m² sem distorções de digitação"
    ],
    tools: ["Python", "Pandas", "Power BI"]
  },
  "projeto-05-engenharia-reversa-bi": {
    area: "Migração e governança",
    title: "Recuperando o conhecimento de relatórios e sistemas antigos",
    problem: "A migração dos relatórios antigos (QlikView e dezenas de arquivos de Power BI) para o Microsoft Fabric estava travada: faltava licença para abrir os arquivos, faltava permissão para ler as regras do banco de dados e os painéis se contradiziam.",
    solution: "Escrevi ferramentas próprias que leem esses arquivos sem precisar do programa original, analisam os relatórios de Power BI e catalogam o que existe, apontando conflitos. Tudo foi documentado em um catálogo com verificação automática para não vazar dados pessoais.",
    results: [
      "Arquivos antigos lidos por inteiro, sem precisar do programa original",
      "Relatórios analisados, com cálculos de mesmo nome e resultados diferentes encontrados",
      "Migração destravada"
    ],
    tools: ["Python", "SQL", "Power BI"]
  }
};

// ============================================================================
// Cartões dos projetos
// ============================================================================
function renderProjects() {
  const grid = document.getElementById("projects-grid");
  if (!grid) return;

  grid.innerHTML = PLAIN_ORDER.map(id => {
    const c = PLAIN_CONTENT[id];
    const proj = portfolioProjects.find(item => item.id === id);
    const company = proj ? proj.company : "";
    return `
    <article class="case-card ${c.featured ? "featured" : ""}">
      <div class="case-meta">
        <span class="case-area">${c.area}</span>
        ${company ? `<span class="case-company">${company}</span>` : ""}
      </div>
      <h3 class="case-title">${c.title}</h3>
      <div>
        <div class="case-label">O problema</div>
        <p class="case-text">${c.problem}</p>
      </div>
      <div>
        <div class="case-label">O que eu fiz</div>
        <p class="case-text">${c.solution}</p>
      </div>
      <div>
        <div class="case-label">O resultado</div>
        <ul class="case-results">
          ${c.results.map(r => `<li>${r}</li>`).join("")}
        </ul>
      </div>
      <div class="chips" aria-label="Ferramentas usadas">
        ${c.tools.map(t => `<span class="chip">${t}</span>`).join("")}
      </div>
      <div class="case-actions">
        <button type="button" class="btn btn-outline btn-sm" onclick="openProjectModal('${id}')">Ver detalhes técnicos</button>
        <a class="btn btn-ghost btn-sm" href="${REPO_CASES_URL}${id}" target="_blank" rel="noopener noreferrer">Código de exemplo ↗</a>
        ${c.simulatorHint ? `<a class="btn btn-ghost btn-sm" href="#area-tecnica" onclick="openTechArea()">Testar simulador</a>` : ""}
      </div>
    </article>`;
  }).join("");
}

// ============================================================================
// Janela de detalhes técnicos
// ============================================================================
function openProjectModal(projectId) {
  const c = PLAIN_CONTENT[projectId];
  const p = portfolioProjects.find(item => item.id === projectId);
  if (!c || !p) return;

  const body = document.getElementById("modal-body");
  body.innerHTML = `
    <div class="modal-head">
      <span class="modal-kicker">Detalhes técnicos · para quem é da área</span>
      <h2>${c.title}</h2>
      <p class="modal-meta">${p.company}</p>
      <p class="modal-lead">${c.problem}</p>
      <p class="modal-note">Os exemplos de código deste projeto usam <strong>dados fictícios</strong>, criados só para demonstrar o método. Nenhum dado de clientes, colaboradores ou das empresas é exibido.</p>
    </div>

    <div class="modal-section">
      <h4>Contexto</h4>
      <p class="modal-p">${p.context}</p>
    </div>

    <div class="modal-section">
      <h4>Desafio técnico</h4>
      <p class="modal-p">${p.challenge}</p>
    </div>

    <div class="modal-section">
      <h4>Arquitetura ponta a ponta</h4>
      <p class="modal-p small">${p.architecture.summary}</p>
      <div class="arch-flow">
        ${p.architecture.nodes.map((n, idx) => `
          <span class="arch-node">${n}</span>
          ${idx < p.architecture.nodes.length - 1 ? '<span class="arch-arrow">→</span>' : ''}
        `).join("")}
      </div>
    </div>

    <div class="modal-section">
      <h4>Decisões técnicas e trade-offs</h4>
      ${p.decisions.map(d => `
        <div class="decision-box">
          <strong>${d.title}</strong>
          <span>${d.detail}</span>
        </div>
      `).join("")}
    </div>

    <div class="modal-section">
      <h4>Produção real × demonstração pública</h4>
      <div class="sim-grid two-col">
        <div class="sim-box">
          <div class="sim-box-title">NO TRABALHO REAL (DOCUMENTADO)</div>
          <p class="modal-p small">${p.demoVsReal.real}</p>
        </div>
        <div class="sim-box">
          <div class="sim-box-title">NA DEMONSTRAÇÃO PÚBLICA (DADOS FICTÍCIOS)</div>
          <p class="modal-p small">${p.demoVsReal.demo}</p>
        </div>
      </div>
    </div>

    <div class="modal-section">
      <h4>Qualidade e como rodar</h4>
      <p class="modal-p small">${p.quality}</p>
      <div class="code-cmd"># Rodar a demonstração com dados fictícios:
${p.demoCommand}

# Rodar os testes automatizados:
${p.testCommand}</div>
      <p class="modal-p small" style="margin-top:0.75rem;"><a class="contact-val" href="${REPO_CASES_URL}${projectId}" target="_blank" rel="noopener noreferrer">Ver o código no GitHub ↗</a></p>
    </div>

    <div class="modal-section">
      <h4>Resultados e lição aprendida</h4>
      <p class="modal-p"><strong>Resultados:</strong> ${p.results}</p>
      <p class="modal-p"><strong>Lição:</strong> ${p.lessons}</p>
    </div>
  `;

  const modal = document.getElementById("project-modal");
  modal.classList.add("open");
  modal.querySelector(".modal-content").scrollTop = 0;
  document.body.classList.add("modal-open");
}

function closeProjectModal() {
  document.getElementById("project-modal").classList.remove("open");
  document.body.classList.remove("modal-open");
}

// ============================================================================
// Área técnica recolhida
// ============================================================================
function openTechArea() {
  const area = document.getElementById("area-tecnica");
  if (area) area.open = true;
}

window.addEventListener("hashchange", () => {
  if (location.hash === "#area-tecnica") openTechArea();
});
window.addEventListener("DOMContentLoaded", () => {
  if (location.hash === "#area-tecnica") openTechArea();
});
