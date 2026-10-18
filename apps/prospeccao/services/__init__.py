"""Serviços do módulo de prospecção.

Reúne o motor de análise (busca no Google Places, download seguro e análise de
sites, PageSpeed, enriquecimento por CNPJ) e a camada de segurança de rede
(fetcher anti-SSRF). O ponto de entrada de alto nível é
``orquestrador.analisar_empresa``.

Este pacote NÃO importa nada dos submódulos no topo de propósito: cada serviço
carrega ``requests``/``tldextract`` e o modelo ``Empresa`` sob demanda, evitando
efeitos colaterais na importação do pacote.
"""
