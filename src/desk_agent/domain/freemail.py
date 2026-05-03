from __future__ import annotations

# Well-known consumer / free-mail providers — skip domain-tagging for these
FREEMAIL_DOMAINS: frozenset = frozenset({
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.co.in",
    "yahoo.ca",
    "yahoo.com.au",
    "ymail.com",
    "hotmail.com",
    "hotmail.co.uk",
    "hotmail.fr",
    "live.com",
    "live.co.uk",
    "outlook.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "protonmail.com",
    "proton.me",
    "pm.me",
    "aol.com",
    "zoho.com",       # personal zoho accounts
    "zohomail.com",
    "mail.com",
    "inbox.com",
    "rediffmail.com",
    "yandex.com",
    "yandex.ru",
    "fastmail.com",
    "gmx.com",
    "gmx.net",
    "gmx.de",
})


def is_freemail(domain: str) -> bool:
    return domain.lower() in FREEMAIL_DOMAINS
