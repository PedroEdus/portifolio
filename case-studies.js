const caseStudies=[
  [
    ["Investigação","A regra estava distribuída entre várias fontes","Antes de modelar, mapeei fontes, chaves, granularidade e o ciclo dos lançamentos. A investigação separou movimentações financeiras reais de registros técnicos gerados pelo ERP e transformou regras operacionais em critérios auditáveis."],
    ["Decisão crítica","O ERP continua sendo o motor","A solução analítica não tenta reconstruir o processo operacional. Ela recebe o status oficial, historiza mudanças, agrega indicadores e aponta exceções. Um cálculo independente permanece como controle e trilha de auditoria."],
    ["Validação","Hipóteses testadas com casos reais","Cada regra foi confrontada com amostras reais e totais do sistema de origem. Esse processo revelou riscos de duplicidade, diferenças entre data operacional e bancária e situações em que incluir uma fonte adicional distorcia o resultado."],
  ],
  [
    ["Problema","Quatro produtos, quatro padrões","Google Ads, Meta Ads, GA4 e Publya existiam como experiências separadas. Isso duplicava conexão, formatação, taxonomias, gráficos e tratamento visual."],
    ["Arquitetura","Núcleo compartilhado e páginas finas","Centralizei autenticação, tema, componentes, gráficos e taxonomias em módulos reutilizáveis. Cada canal ganhou um carregador próprio com cache; a página ficou responsável apenas pela experiência analítica."],
    ["Resiliência","Dados vazios não derrubam o produto","As fontes são tratadas defensivamente. Quando um canal está sem dados, o painel explica a ausência e mantém os indicadores consolidados com as demais fontes disponíveis."],
  ],
  [
    ["Investigação","Transformar páginas em um esquema","O HTML do portal público foi analisado para localizar informações distribuídas entre diferentes componentes. Seletores estruturais e expressões regulares transformaram rótulos visuais em atributos consistentes."],
    ["Implementação","Coleta leve e reproduzível","Requisições HTTP e parsing de HTML foram suficientes para consultar as páginas e interpretar o conteúdo. O pipeline limpa rótulos, separa campos compostos, padroniza textos e converte cada registro em uma linha."],
    ["Saída","Histórico acumulado para análise","Os registros são consolidados em uma base histórica com informações técnicas dos projetos, permitindo análises de mercado sem depender de consultas manuais página por página."],
  ],
  [
    ["Problema","Texto livre impedia segmentação","Profissões, bairros, endereços e respostas chegavam com grafias diferentes e chaves incompletas. Antes da análise, foi necessário criar uma camada de normalização e enriquecimento."],
    ["IA aplicada","LLM local como fallback controlado","Valores conhecidos seguem um mapa determinístico. Somente profissões não resolvidas são classificadas por uma LLM executada localmente via Ollama, usando exemplos e uma lista fechada de categorias. A IA aumenta a cobertura sem substituir regras verificáveis."],
    ["Enriquecimento","Do respondente ao contexto geográfico","O pipeline combina informações demográficas, profissionais e geográficas. Coordenadas e cálculo de distância transformam endereços em faixas comparáveis, úteis para estudar a relação entre clientes e empreendimentos."],
  ],
];
document.querySelectorAll(".project").forEach((project,index)=>{const section=document.createElement("section");section.className="deepDive";section.innerHTML=`<div class="deepDiveIntro"><span>Como o projeto foi resolvido</span><p>Além da ferramenta: investigação, escolha técnica e evidência.</p></div><div class="deepDiveGrid">${caseStudies[index].map(([label,title,text])=>`<div class="deepDiveItem"><span>${label}</span><h4>${title}</h4><p>${text}</p></div>`).join("")}</div>`;project.querySelector(".projectFooter").before(section)});
