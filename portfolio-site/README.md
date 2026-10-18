# Site do Portfólio — `portfolio-site/`

Site estático e responsivo (HTML, CSS e JavaScript sem dependências de build), publicado no **GitHub Pages** em `https://pedroedus.github.io/portifolio/` pelo workflow `.github/workflows/pages.yml`, que envia somente esta pasta.

---

## 1. Estrutura

```text
portfolio-site/
├── .nojekyll
├── index.html                 # Página: topo, três passos, projetos, hábitos, trajetória, ferramentas, área técnica e contato
├── README.md
└── assets/
    ├── css/styles.css         # Visual (tema escuro por padrão, tema claro opcional)
    ├── img/og.jpg             # Imagem de compartilhamento (LinkedIn, WhatsApp)
    ├── js/
    │   ├── cases.js           # Textos dos 6 projetos em linguagem simples + janela "Ver detalhes técnicos"
    │   └── app.js             # Simuladores da área técnica, tema, cópia de contato e dados de apoio (fallback)
    └── data/projects.json     # Detalhes técnicos de cada projeto (aparecem em "Ver detalhes técnicos")
```

---

## 2. Duas camadas de leitura

1. **Camada simples (padrão):** cada projeto é contado em *problema → o que eu fiz → resultado*, com as ferramentas só como etiquetas. Os textos ficam em `assets/js/cases.js`.
2. **Camada técnica (opcional):** o botão "Ver detalhes técnicos" abre a arquitetura e as decisões de cada projeto (dados de `assets/data/projects.json`). A **área técnica** recolhida, no fim da página, reúne os 3 simuladores e a matriz de tecnologias.

Todos os exemplos usam **dados fictícios**; nenhum dado de clientes ou das empresas é exibido.

---

## 3. Como visualizar localmente

```bash
cd portfolio-site
python -m http.server 8080
```

Em seguida, acesse `http://localhost:8080`. Abrir o `index.html` direto no navegador também funciona (o `app.js` tem um espelho dos dados para o protocolo `file://`).

---

## 4. Como atualizar o conteúdo

| O que mudar | Onde |
| :--- | :--- |
| Textos e resultados dos cartões de projeto | `assets/js/cases.js` |
| Números do topo, trajetória e ferramentas | `index.html` |
| Detalhes técnicos de cada projeto | `assets/data/projects.json` **e** o bloco `FALLBACK_PORTFOLIO_DATA` em `assets/js/app.js` (espelho; mantenha os dois iguais) |
| Contatos (LinkedIn, e-mail, telefone) | seção `<footer id="contato">` em `index.html`, bloco `CONFIG` em `assets/js/app.js` e `profile.contacts` em `projects.json` |

Antes de publicar qualquer mudança, rode `python verify_portfolio.py` na raiz do repositório (testes dos 6 cases e varredura de segredos) e confira que nenhum nome de empresa ou dado interno entrou nos textos.
