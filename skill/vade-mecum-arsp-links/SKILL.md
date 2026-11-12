---
name: vade-mecum-arsp-links
description: Liga as citações de normas da ARSP (gás canalizado do Espírito Santo) em documentos Word (.docx) ao site Vade-mécum ARSP Gás. Cada citação como "art. 43, § 7º, da Resolução ARSP nº 46/2021", "Cláusula IX do Contrato de Concessão" ou "item 23 do Anexo I da Resolução ARSP nº 84/2025" vira hyperlink para o dispositivo exato no site, com dica de tela (ScreenTip) mostrando o texto do artigo, parágrafo, inciso, cláusula ou item citado. Use sempre que gerar, editar ou receber um .docx que cite resoluções ou decisões da ARSP, a LC 827/2016, a Lei 11.173/2020 ou o contrato de concessão da ES Gás, e quando o usuário pedir os links do vade-mécum num documento.
---

# Links do Vade-mécum ARSP Gás em documentos Word

O script `scripts/vincular.py`, nesta pasta, lê um .docx e acha as citações com o mesmo detector do site https://brayanblail.github.io/vade-mecum-arsp/. Grava uma cópia em que cada citação é um hyperlink para o dispositivo, e a dica de tela do Word mostra o texto citado. Só usa a biblioteca padrão do Python.

## Passo a passo

1. **Gere o documento normalmente** (com a skill de Word/docx, se houver). Escreva cada citação com o ato junto, por extenso, que é como o detector reconhece:
   - "art. 43, § 7º, da Resolução ARSP nº 46/2021", "§ 7º do art. 43 da Res. ARSP 046/2021" ou "Resolução ARSP nº 46/2021, art. 43";
   - "incisos III e XIII do art. 7º da Lei Complementar nº 827/2016"; "artigos 37 a 39 da Resolução ARSP nº 46/2021" (um link por número);
   - "Cláusula IX do Contrato de Concessão"; "item 8.25 da Cláusula VIII do contrato de concessão"; "cláusula 12.12.1 do contrato de concessão";
   - "item 23 do Anexo I da Resolução ARSP nº 84/2025";
   - "Decisão ARSP/DG nº 007/2026"; "Lei nº 11.173/2020"; "Resolução ARSP nº 114/2026" (link para o ato inteiro).

   O ato precisa do órgão: "Resolução nº 46/2021" (sem "ARSP") e "RN 46" não são reconhecidas.
2. **Rode o script** (troque `<pasta>` pela pasta deste SKILL.md):
   ```bash
   python <pasta>/scripts/vincular.py entrada.docx saida.docx
   ```
3. **Leia o relatório**:
   - "Links criados" lista cada citação e o dispositivo de destino. Os marcados `[INFERIDO: confira]` foram deduzidos do contexto; avise o usuário.
   - "a citação não diz o ato" (ex.: "o art. 43" sozinho): reescreva a citação com o ato. Se o documento inteiro trata de um só ato, rode de novo com `--padrao <id do ato>` (os links ficam como inferidos).
   - "ato fora da base do site": o site ainda não tem esse ato; não há link.
   - "o trecho está num link, campo ou revisão do Word": aceite ou rejeite as revisões e rode de novo.
4. **Entregue o arquivo de saída** e diga ao usuário quantos links foram criados, quais são inferidos e quais citações ficaram sem link. No Word, a dica de tela aparece ao passar o mouse sobre o link, e Ctrl+clique abre o site no dispositivo citado.

Para testar uma frase antes de escrever o documento:
```bash
python <pasta>/scripts/vincular.py --texto "art. 43, § 7º, da Resolução ARSP nº 46/2021"
```

## Opções

| opção | efeito |
|---|---|
| `--padrao ID` | ato das citações que não dizem o ato (ex.: `res-arsp-046-2021`); os links ficam como inferidos |
| `--sem-contrato` | num documento que cita o contrato de concessão, "Cláusula IX" sem o nome do contrato não vira link para o contrato |
| `--sem-externos` | não liga leis federais e a Constituição ao LexML |
| `--limite N` | tamanho máximo da dica de tela (padrão 255, o limite do Word) |
| `--offline` | não tenta baixar a base mais nova do site |
| `--json ARQ` | grava também o relatório em JSON |
| `--atos` | lista os atos da base com os ids |

## Como funciona e limites

- Processa o corpo, as tabelas, as notas de rodapé e as notas de fim. Links que já existem não mudam, então o script pode rodar de novo sobre a saída. Texto dentro de revisões controladas ou de campos não vira link.
- O link fica azul e sublinhado. A dica de tela tem o rótulo ("Res. ARSP 046/2021 · Art. 43, § 7º") e o texto do dispositivo, cortado com "…" no limite do Word (255 caracteres).
- Num documento que cita o "contrato de concessão" em algum trecho, "Cláusula IX" sozinha liga ao contrato como inferido, como no site. Isso não vale no parágrafo que fala do CUSD.
- Base: versão be65be27, com 17 atos. O script tenta baixar a base mais nova do site (`vinculos.json`). Se a rede do ambiente bloquear, usa esta cópia e avisa no relatório. Para liberar, inclua `brayanblail.github.io` nos domínios permitidos da execução de código.
- As decisões da aba "A conferir" do site (link aceito, tirado ou corrigido) não valem aqui: o script liga o que o detector acha.

## Atos da base (versão be65be27)

| id | ato | situação | ementa |
|---|---|---|---|
| `lc-827-2016` | LC 827/2016 | Vigente | Cria a Agência de Regulação de Serviços Públicos - ARSP, em decorrência da fusão da ARSI e da ASPE, e dá outras providências. |
| `lei-11173-2020` | Lei 11.173/2020 | Vigente | Dispõe sobre normas para o mercado livre de gás canalizado no âmbito do Estado do Espírito Santo e dá outras providências. |
| `contrato-concessao-2020` | Contrato de Concessão | Vigente | Contrato de concessão para exploração do serviço público de distribuição de gás canalizado que entre si celebram o Estado do Espírito… |
| `res-arsp-046-2021` | Res. ARSP 046/2021 | Vigente | Dispõe sobre as regras para o Mercado Livre de Gás Canalizado e as condições para a prestação do Serviço Público de Distribuição de Gás… |
| `res-arsp-048-2021` | Res. ARSP 048/2021 | Vigente | Define infrações, penalidades e as regras do processo sancionador à prestadora de serviços públicos de distribuição de gás canalizado no… |
| `res-arsp-053-2021` | Res. ARSP 053/2021 | Vigente | Dispõe sobre o modelo do Contrato de Uso do Serviço de Distribuição – CUSD a ser celebrado entre a Concessionária e os Agentes Livres de… |
| `res-arsp-059-2022` | Res. ARSP 059/2022 | Vigente | Dispõe sobre os indicadores de segurança do serviço público de distribuição de gás canalizado, revoga a Resolução ASPE nº 004/2013 e dá… |
| `res-arsp-061-2023` | Res. ARSP 061/2023 | Vigente | Dispõe sobre procedimento de reajuste da tarifa do gás canalizado contemplando apuração e recuperação dos saldos provocados pelas… |
| `res-arsp-063-2023` | Res. ARSP 063/2023 | Vigente | Dispõe sobre os indicadores de qualidade do atendimento comercial do serviço público de distribuição de gás canalizado e dá outras… |
| `res-arsp-067-2023` | Res. ARSP 067/2023 | Vigente | Dispõe sobre os indicadores de qualidade do produto e do serviço público de distribuição de gás canalizado e dá outras providências. |
| `res-arsp-080-2024` | Res. ARSP 080/2024 | Vigente | Estabelece os critérios para a definição da base de remuneração regulatória aplicável às revisões tarifárias ordinárias da Companhia de… |
| `res-arsp-084-2025` | Res. ARSP 084/2025 | Vigente | Estabelece a metodologia de revisão da margem média de distribuição aplicável à 1ª Revisão Tarifária Ordinária da Companhia de Gás do… |
| `res-arsp-091-2025` | Res. ARSP 091/2025 | Vigente | Dispõe sobre os resultados da 1ª Revisão Tarifária Ordinária da Companhia de Gás do Espírito Santo – ES Gás e estabelece a estrutura… |
| `res-arsp-101-2026` | Res. ARSP 101/2026 | Vigente | Define a tabela tarifária para o segmento termoelétrico no âmbito do Estado do Espírito Santo. |
| `res-arsp-106-2026` | Res. ARSP 106/2026 | Vigente | Reajuste tarifário de agosto de 2026 – ES Gás. |
| `res-arsp-114-2026` | Res. ARSP 114/2026 | Vigente | Dispõe sobre as Condições Gerais da Prestação dos Serviços Locais de Gás Canalizado no Estado do Espírito Santo. |
| `dec-arsp-dg-007-2026` | Decisão ARSP/DG 007/2026 | Vigente | Homologa o reajuste tarifário em função da alteração do preço do gás canalizado, adotando Preço Médio do Gás, nos termos da Resolução ARSP… |
