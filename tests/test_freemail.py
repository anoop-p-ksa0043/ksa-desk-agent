from desk_agent.domain.freemail import is_freemail


def test_known_freemail_domains_are_detected():
    for domain in ["gmail.com", "yahoo.com", "outlook.com", "icloud.com", "hotmail.com"]:
        assert is_freemail(domain), f"{domain} should be detected as freemail"


def test_corporate_domains_are_not_freemail():
    for domain in ["acme.com", "bigcorp.io", "enterprise.co.uk", "startup.ai"]:
        assert not is_freemail(domain), f"{domain} should not be freemail"


def test_case_insensitivity():
    assert is_freemail("Gmail.COM")
    assert not is_freemail("ACME.COM")
