---
name: vade-mecum-arsp-links
description: Liga as citações de normas da ARSP (gás canalizado do Espírito Santo) em documentos Word (.docx) ao site Vade-mécum ARSP Gás. Cada citação como "art. 43, § 7º, da Resolução ARSP nº 46/2021", "Cláusula IX do Contrato de Concessão" ou "item 23 do Anexo I da Resolução ARSP nº 84/2025" vira hyperlink para o dispositivo exato no site, com dica de tela (ScreenTip) mostrando o texto do artigo, parágrafo, inciso, cláusula ou item citado. Use sempre que gerar, editar ou receber um .docx que cite resoluções ou decisões da ARSP, a LC 827/2016, a Lei 11.173/2020 ou o contrato de concessão da ES Gás, e quando o usuário pedir os links do vade-mécum num documento.
---

# Links do Vade-mécum ARSP Gás em documentos Word

O script `scripts/vincular.py`, nesta pasta, lê um .docx e acha as citações com o mesmo detector do site {{SITE}}. Grava uma cópia em que cada citação é um hyperlink para o dispositivo, e a dica de tela do Word mostra o texto citado. Só usa a biblioteca padrão do Python.

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
- Base: versão {{VERSAO}}, com {{N_ATOS}} atos. O script tenta baixar a base mais nova do site (`vinculos.json`). Se a rede do ambiente bloquear, usa esta cópia e avisa no relatório. Para liberar, inclua `brayanblail.github.io` nos domínios permitidos da execução de código.
- As decisões da aba "A conferir" do site (link aceito, tirado ou corrigido) não valem aqui: o script liga o que o detector acha.

## Atos da base (versão {{VERSAO}})

{{ATOS}}
