from __future__ import annotations

import unittest
from unittest.mock import patch

from egressd import EgressError, validate_url


GLOBAL_DNS = [(2, 1, 6, "", ("93.184.216.34", 443))]
PRIVATE_DNS = [(2, 1, 6, "", ("127.0.0.1", 443))]


class EgressValidationTests(unittest.TestCase):
    @patch("egressd.socket.getaddrinfo", return_value=GLOBAL_DNS)
    def test_exact_allowlisted_https_host_is_allowed(self, _: object) -> None:
        parts, addresses = validate_url("https://docs.python.org/3/", {"docs.python.org"})
        self.assertEqual(parts.hostname, "docs.python.org")
        self.assertEqual(addresses, ["93.184.216.34"])

    @patch("egressd.socket.getaddrinfo", return_value=PRIVATE_DNS)
    def test_private_dns_answer_is_rejected(self, _: object) -> None:
        with self.assertRaises(EgressError):
            validate_url("https://docs.python.org/3/", {"docs.python.org"})

    @patch("egressd.socket.getaddrinfo", return_value=GLOBAL_DNS)
    def test_scheme_credentials_port_and_subdomain_are_rejected(self, _: object) -> None:
        cases = (
            "http://docs.python.org/",
            "https://user:pass@docs.python.org/",
            "https://docs.python.org:444/",
            "https://evil.docs.python.org/",
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(EgressError):
                validate_url(value, {"docs.python.org"})


if __name__ == "__main__":
    unittest.main()
