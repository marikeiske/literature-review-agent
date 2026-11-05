"""O teste diário pergunta coisas diferentes a cada dia, sem repetir, e não mexe em nada versionado."""
import teste_diario


def test_cada_dia_tem_perguntas_novas():
    itens = [{"id": f"A{n:03d}", "artigo": "X", "paginas": {1}} for n in range(109)]
    vistos, negs, livres = set(), set(), set()
    for dia in range(1, teste_diario.DIAS + 1):
        afs, neg, livre = teste_diario.conjunto_do_dia(dia, itens)
        ids = {a["id"] for a in afs}
        assert len(ids) == teste_diario.POR_DIA
        assert not ids & vistos, f"dia {dia} repetiu afirmação"
        vistos |= ids
        negs.add(neg["id"])
        livres.add(livre)
    assert len(negs) == teste_diario.DIAS and len(livres) == teste_diario.DIAS
    # Mesmo dia, mesma escolha (dá para refazer um dia que falhou)
    assert teste_diario.conjunto_do_dia(3, itens) == teste_diario.conjunto_do_dia(3, list(reversed(itens)))


def test_saida_fica_fora_do_git():
    assert teste_diario.PASTA.relative_to(teste_diario.RAIZ).parts[0] == "logs"
