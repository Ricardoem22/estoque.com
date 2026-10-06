# email_envio.py
# Envio de e-mail pelo SMTP (Gmail com senha de app no PythonAnywhere).
import smtplib
from email.message import EmailMessage

import config


def email_configurado():
    return bool(config.EMAIL_USUARIO and config.EMAIL_SENHA)


def enviar_email(para, assunto, texto):
    mensagem = EmailMessage()
    mensagem["From"] = f"Gestor Full de Restaurante <{config.EMAIL_USUARIO}>"
    mensagem["To"] = para
    mensagem["Subject"] = assunto
    mensagem.set_content(texto)
    with smtplib.SMTP(config.EMAIL_SMTP, config.EMAIL_PORTA, timeout=20) as servidor:
        if config.EMAIL_PORTA == 587:
            servidor.starttls()
        if config.EMAIL_SMTP != "localhost":
            servidor.login(config.EMAIL_USUARIO, config.EMAIL_SENHA)
        servidor.send_message(mensagem)
