# 📊 Sistema de Análise de Migrações Móvel (CRM)

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-323330?style=for-the-badge&logo=javascript&logoColor=F7DF1E)

> Uma aplicação web robusta projetada para automatizar e otimizar a análise de migrações de planos de telefonia móvel (CRM). O sistema processa planilhas complexas, aplica regras de negócio rigorosas e gera um dashboard financeiro e de produtos instantaneamente.

---

## 💻 Sobre o Projeto

No cenário de telecomunicações, analisar a base de clientes (Mailing) e decidir quais ofertas de Upgrade, Downgrade ou Manutenção (Padrão) são elegíveis para cada linha é um trabalho demorado se feito manualmente.

Este projeto resolve esse problema através de uma arquitetura **desacoplada (Frontend/Backend)**. O motor de regras no backend, construído em **Python (Pandas + Flask)**, lê e processa a planilha do usuário, calculando o "Delta" financeiro de cada cliente. O frontend consome essa API de forma assíncrona, exibindo um painel limpo, moderno e focado na experiência do usuário.

### 📸 Preview da Aplicação

> **Nota:** *Adicione aqui uma imagem da sua tela final.*
> `![Dashboard de Resultados](caminho/para/sua/imagem.png)`

---

## ✨ Principais Funcionalidades

- **Upload Dinâmico:** Envio de planilhas Excel (`.xlsx`, `.xls`) direto pelo navegador.
- **Motor de Regras de Negócio Customizado:** 
  - Diferenciação por tempo de base (M0-M6, M7-M16, M17+).
  - Cálculo automático de variação percentual para aprovação de Upgrades ($\ge 10\%$ ou $\ge 5\%$).
  - Bloqueio de retrocesso (Downgrade) para planos novos e liberação controlada para clientes antigos (M23+), com alertas de limite.
- **Processamento de Dados Rápido:** Utilização da biblioteca `Pandas` para manipulação de grandes volumes de dados de forma vetorizada.
- **Dashboard Resumo:** Tabelas de contagem de linhas, faturamento atual vs. novo e status de aprovação.
- **Extrator de Franquia:** Algoritmo via Expressões Regulares (RegEx) para calcular automaticamente a volumetria em Gigabytes (GB) de todas as ofertas lidas na planilha.

---

## ⚙️ Arquitetura e Tecnologias

A aplicação foi dividida em duas camadas independentes para facilitar a manutenção e o deploy em servidores modernos (como VPS ou serviços em nuvem):

### Backend (API RESTful)
- **Python 3.x**
- **Flask** (Criação do servidor e roteamento web)
- **Pandas & NumPy** (Engenharia e processamento de dados)
- **OpenPyXL** (Leitura de pacotes MS Excel)
- **Flask-CORS** (Comunicação segura com o frontend)

### Frontend (Client-side)
- **HTML5 & CSS3** (Design responsivo, paleta de cores UI/UX focada em conversão)
- **Vanilla JavaScript (ES6)** (Consumo assíncrono da API via `Fetch`, manipulação de DOM e uploads)

---

## 🚀 Como Executar o Projeto Localmente

Siga os passos abaixo para rodar a aplicação na sua máquina.

### Pré-requisitos
- Python 3.10+ instalado.
- Navegador Web moderno.

### Passo 1: Configurando o Backend
1. Clone este repositório:
   ```bash
   git clone [https://github.com/SEU-USUARIO/meu-projeto-delta.git](https://github.com/SEU-USUARIO/meu-projeto-delta.git)