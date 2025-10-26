import os, smtplib, ssl
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = "587"
SMTP_USER = "gaurikaushik2013@gmail.com"
SMTP_PASS = "awawjrohjhyglchm"
NOTIFY_TO = "gaurikaushik2013@gmail.com"
FROM = "Form Tester <gaurikaushik2013@gmail.com>"

print("SMTP_HOST:", SMTP_HOST, "SMTP_PORT:", SMTP_PORT, "SMTP_USER:", SMTP_USER, "NOTIFY_TO:", NOTIFY_TO)

if not (SMTP_HOST and SMTP_USER and SMTP_PASS and NOTIFY_TO):
    print("Missing one or more required env vars (SMTP_HOST/SMTP_USER/SMTP_PASS/NOTIFY_TO).")
    raise SystemExit(1)

msg = EmailMessage()
msg["Subject"] = "Form Tester — SMTP test"
msg["From"] = FROM
msg["To"] = NOTIFY_TO
msg.set_content("This is a test email from Form Tester at " + __import__("datetime").datetime.utcnow().isoformat())

# try STARTTLS (port 587)
try:
    print("Attempting SMTP starttls...")
    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
    server.set_debuglevel(1)   # prints SMTP dialogue
    server.ehlo()
    server.starttls(context=ssl.create_default_context())
    server.ehlo()
    server.login(SMTP_USER, SMTP_PASS)
    server.send_message(msg)
    server.quit()
    print("SMTP test email sent successfully.")
except Exception as e:
    print("STARTTLS attempt failed:", type(e).__name__, str(e))
    # try SMTPS (port 465) fallback
    try:
        print("Attempting SMTPS (SSL) on port 465...")
        server = smtplib.SMTP_SSL(SMTP_HOST, 465, timeout=20)
        server.set_debuglevel(1)
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        print("SMTPS test email sent successfully.")
    except Exception as e2:
        print("SMTPS attempt failed:", type(e2).__name__, str(e2))
        raise
