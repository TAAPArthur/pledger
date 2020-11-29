import unittest
from .pledger import *


class CurrencyTest(unittest.TestCase):
    def test_get_symbol(self):
        for token in ["$1234", "-$1234", "$-123"]:
            with self.subTest(token=token):
                self.assertEqual("$", getCurrencySymbol(token))


class TransactionTest(unittest.TestCase):
    def setUp(self):
        self.root = Account()

    def test_init(self):
        t = Transaction("2000/01/01", "*", self.root)
        t.addItem("Assets", "$100")
        t.commit()
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 100)

    def test_transaction(self):
        for i in range(1, 10):
            t = Transaction("2000/01/01", "title", self.root)
            t.addItem("Assets", "$123")
            t.addItem("Expenses")
            t.commit()
            self.assertEqual(self.root.getAccount("Assets").getValue("$"), 123 * i)
            self.assertEqual(self.root.getAccount("Expenses").getValue("$"), -123 * i)

    def test_quantity(self):
        q = 2
        N = 10
        for op in ["*", "-", "+", "/"]:
            t = Transaction("2000/01/01", "title", self.root)
            name = "Assets:" + op
            expr = "({} {} ${})".format(q, op, N)
            t.addItem(name, expr)
            t.addItem("Expenses")
            t.commit()
            self.assertEqual(self.root.getAccount(name).getValue("$"), eval(expr.replace("$", "")))

    def test_conversion(self):
        t = Transaction("2000/01/01", "title", self.root)
        t.addItem("Assets", "10 STOCK @ $100")
        t.addItem("Expenses")
        t.commit()
        self.assertEqual(self.root.getAccount("Assets").getValue("STOCK"), 10)
        self.assertEqual(self.root.getAccount("Expenses").getValue("STOCK"), -10)
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), -1000)
        self.assertEqual(self.root.getAccount("Expenses").getValue("$"), 1000)

    def dummyAdd(self, accountName, valueStr):
        t = Transaction("2000/01/01", "Test", self.root)
        t.addItem(accountName, valueStr)
        t.addItem("Dummy")
        t.commit()

    def test_validation(self):
        self.dummyAdd("Assets", "$100")
        self.dummyAdd("Assets", "$10=$110")
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 110)
        self.dummyAdd("Assets", "$10")
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 120)
        self.dummyAdd("Assets", "=$130")
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 130)

    def test_post_validation(self):
        t = Transaction("2000/01/01", "Test", self.root)
        t.addItem("Assets", "$100")
        t.addItem("Expenses")
        t.commit()
        t = Transaction("2000/01/01", "Test", self.root)
        t.addItem("Assets", "=$200")
        t.addItem("Expenses", "$10")
        try:
            t.commit()
            assert False
        except:
            pass


if __name__ == '__main__':
    unittest.main()
