"""Módulo de Marketing por E-mail (adendo 3 — MÓDULO 5).

App plugável e AUTOCONTIDO: o remetente e a configuração SMTP ficam no próprio
módulo (modelo ``ConfiguracaoEnvio``) e o envio abre a conexão via
``get_connection`` do módulo — sem depender das configs globais ``EMAIL_*`` do
Django. Ver ``apps.py::ready()`` para o registro no núcleo.
"""
