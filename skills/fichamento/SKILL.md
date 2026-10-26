---
name: fichamento
description: Use quando pedirem o fichamento completo de UM artigo do corpus (objetivo, método, resultados, limitações), com página em cada item.
---

# Fichamento de um artigo

Objetivo: um resumo estruturado de um único artigo, em que cada item pode ser
conferido na página citada.

## Passos (orçamento: 4 leituras ou buscas no total)

1. Leia a página 1 (`ler_pagina`): resumo e introdução dão o objetivo.
2. Faça 3 buscas com `buscar_trechos`, restritas ao artigo e em inglês:
   - método: "method approach architecture implementation"
   - resultados: "results speedup performance evaluation"
   - limitações: "limitation future work drawback"
3. Não leia páginas extras: o harness encerra as buscas depois de 4.

## Formato da saída

Quatro seções, nesta ordem: **Objetivo**, **Método**, **Resultados**, **Limitações**.
Em cada seção, uma afirmação por linha, começando com "- " e terminando com [Id p.N].

## Regras

- Se uma seção não tiver suporte no que você leu, escreva "- Não consta no material aberto."
- Números e unidades exatamente como na página.
- Não misture artigos no mesmo fichamento.
- Se o artigo se contradiz (por exemplo, um valor no resumo e outro nos resultados),
  registre os dois, cada um com sua página.
