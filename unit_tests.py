import unittest
from .pledger import *
import logging
from decimal import Decimal


class CurrencyTest(unittest.TestCase):
    def test_get_symbol(self):
        for token in ["$1234", "-$1234", "$-123"]:
            with self.subTest(token=token):
                self.assertEqual("$", getCurrencySymbol(token))


class TransactionTest(unittest.TestCase):
    def setUp(self):
        self.root = Account()

    def assertEqual(self, A, B):
        if isinstance(A, Decimal):
            super().assertEqual(A.quantize(Decimal(".0000000001")), Decimal(round(B, 10)).quantize(Decimal(".0000000001")))
        else:
            super().assertEqual(A, B)

    def test_init(self):
        t = Transaction("2000/01/01", "*", self.root)
        t.addItem("Assets", "$100")
        t.commit()
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 100)

    def test_transaction(self):
        for i in range(1, 10):
            with self.subTest(i=i):
                t = Transaction("2000/01/01", "title", self.root)
                t.addItem("Assets", "$123")
                t.addItem("Expenses")
                t.commit()
                self.assertEqual(self.root.getAccount("Assets").getValue("$"), 123 * i)
                self.assertEqual(self.root.getAccount("Expenses").getValue("$"), -123 * i)

    def test_transaction_decimal(self):
        t = Transaction("2000/01/01", "title", self.root)
        t.addItem("Assets", "$103.020406")
        t.addItem("Assets", "$20.103050")
        t.addItem("Expenses", "$-123.123456")
        t.commit()
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 123.123456)

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
        t.addItem("Assets")
        t.commit()
        self.assertEqual(self.root.getAccount("Assets").getValue("STOCK"), 10)
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), -1000)

    """
    def test_out_of_order_validation(self):
        t = Transaction("2000/01/01", "Test", self.root)
        t.addItem("Assets", "$10")
        t.addItem("Assets", "=$0")
        t.addItem("Assets", "$10")
        t.addItem("Dummy")
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 10)
    """

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
        self.dummyAdd("Assets", "=$160")
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 160)

    def test_validation_decimal(self):
        self.dummyAdd("Assets", "$1.0")
        self.dummyAdd("Assets", "$.10=$1.10")
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 1.10)
        self.dummyAdd("Assets", "$.10")
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 1.20)
        self.dummyAdd("Assets", "=$1.60")
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), 1.60)

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


class ParserTest(unittest.TestCase):
    lines = """
2000/01/01 * Start
	Assets:Credit					         -$50
    Expenses:Food                           $0
2000/01/01 Transaction 1
    Expenses:Food                           $100
    Assets:Credit                           =-$150

2000/01/02 Transaction 2
    Expenses:Food                           $150
    Assets:Credit                           -$150=-$300
; Comment
2000/01/03 Transaction 3
    Expenses:Food                           $300; Comment
    Assets:Credit                           =-$600
    """.splitlines()

    def test_parse_file(self):
        root, transactions = parse_file(self.lines)
        assert(root.children)
        assert(transactions)

    def test_balance(self):
        parse_args(["bal"], self.lines)

    def test_register(self):
        parse_args(["reg"], self.lines)


if __name__ == '__main__':
    logging.basicConfig(format='[%(filename)s:%(lineno)s]%(levelname)s:%(message)s', level=logging.DEBUG)
    logger = logging.getLogger()
    stream_handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(stream_handler)

    unittest.main()
