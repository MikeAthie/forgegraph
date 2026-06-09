from __future__ import annotations

import getpass
import json
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

FROM_EMAIL = "athiemiguel02@gmail.com"
TO_EMAIL = "admin@intlabs.dev"
SUBJECT = "Legacy Optical Noir — ForgeGraph/Codex company run deliverables ready"
PACKAGE_DIR = Path("../.hermes/legacy_client_handoff_email")
ZIP_PATH = PACKAGE_DIR / "legacy_optical_noir_handoff_package.zip"
BODY_TEXT_PATH = PACKAGE_DIR / "email_body.md"
BODY_HTML_PATH = PACKAGE_DIR / "email_body.html"


def main() -> None:
    password = getpass.getpass("Gmail password or app password: ")
    message = EmailMessage()
    message["From"] = f"ForgeGraph Atlas <{FROM_EMAIL}>"
    message["To"] = TO_EMAIL
    message["Subject"] = SUBJECT
    message.set_content(BODY_TEXT_PATH.read_text(encoding="utf-8"))
    message.add_alternative(BODY_HTML_PATH.read_text(encoding="utf-8"), subtype="html")
    attachment = ZIP_PATH.read_bytes()
    message.add_attachment(
        attachment,
        maintype="application",
        subtype="zip",
        filename=ZIP_PATH.name,
    )
    with smtplib.SMTP_SSL(
        "smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30
    ) as server:
        server.login(FROM_EMAIL, password)
        refused = server.send_message(message)
    print(
        json.dumps(
            {
                "sent": True,
                "from": FROM_EMAIL,
                "to": TO_EMAIL,
                "subject": SUBJECT,
                "attachment": str(ZIP_PATH.resolve()),
                "refused": refused,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
