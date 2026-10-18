"""App 'nucleo': dashboard, registro de módulos (a BASE) e segurança compartilhada.

O núcleo é o ponto de extensão do sistema: expõe o ``registro`` de módulos em
``apps.nucleo.modulos`` e NUNCA importa apps-módulo (ex.: apps.prospeccao).
Cada módulo se registra sozinho no seu próprio ``apps.py::ready()``.
"""
