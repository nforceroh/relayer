"""The recipient store contract, run against the in-memory adapter."""

import unittest

from app.store import InMemoryRecipientStore
from tests.store_contract import StoreContractTests


class InMemoryStoreTests(StoreContractTests, unittest.TestCase):
    def make_store(self):
        return InMemoryRecipientStore()


if __name__ == "__main__":
    unittest.main()