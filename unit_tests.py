import unittest
from decimal import Decimal
from pledger import getCurrencySymbol, Account, Transaction, parse_file, parse_args


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

    def test_conversion_per_unit(self):
        t = Transaction("2000/01/01", "title", self.root)
        t.addItem("Assets", "10 STOCK @ $100")
        t.addItem("Assets")
        t.commit()
        self.assertEqual(self.root.getAccount("Assets").getValue("STOCK"), 10)
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), -1000)

    def test_conversion_total(self):
        t = Transaction("2000/01/01", "title", self.root)
        t.addItem("Assets", "10 STOCK @@ $100")
        t.addItem("Assets")
        t.commit()
        self.assertEqual(self.root.getAccount("Assets").getValue("STOCK"), 10)
        self.assertEqual(self.root.getAccount("Assets").getValue("$"), -100)

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

    def test_validation_assert_equal_fail(self):
        t = Transaction("2000/01/01", "Test", self.root)
        t.addItem("Assets", "$1")
        t.addItem("Expenses", "$1")
        self.assertRaises(ValueError, t.commit)

    def test_validation_imblanced(self):
        accountName = "Assets"
        for value in (-10, 10):
            with self.subTest(value=value):
                t = Transaction("2000/01/01", "Test", Account())
                t.addItem(accountName, str(value))
                t.addItem("Dummy", "=0")
                self.assertRaises(ValueError, t.commit)

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


class PeriodicTransactionTest(unittest.TestCase):
    lines = """
2000/01/01 * Start
    Assets:Credit					        =$0
    Expensese:Credit					        =$1

~daily
    Assets:Credit:D					       -$1
    Expenses

~monthly
    Assets:Credit:M					       -$100
    Expenses

~yearly
    Expenses
    Assets:Credit:Y					       -$1000

2000/01/02 DailyTest
    Assets:Debit					       -$.01
    Expenses

2000/02/01 MonthlyTest
    Assets:Debit					        -$10
    Expenses

2001/01/01 YearlyTest
    Assets:Debit					       -$100
    Expenses:A
""".splitlines()

    def test_periodic_transaction(self):
        root, transactions = parse_file(self.lines)
        self.assertEqual(int(root.getAccount("Assets:Credit").getValue("$")), -(366 * 1 + 12 * 100 + 1 * 1000))


class AutoTransactionTest(unittest.TestCase):
    perecent_lines = """
2000/01/01 * Start
    Assets:Credit					         -$50
    Expenses:Food                           $0
= Assets:Credit
    Assets:CashBack                         .1

2000/01/02 Transaction 2
    Assets:Credit                           -$100
    Expenses:Food                           $110
""".splitlines()
    abs_lines = """
2000/01/02 Transaction 3
    Assets:Debit                           -$100
    Expenses:Food                           $100

= Assets:Debit
    Assets:Debit                          -$.1

2000/01/02 Transaction 4
    Assets:Debit                           -$100
    Expenses:Food                          $100.1
    """.splitlines()

    def test_auto_transaction_percent(self):
        root, transactions = parse_file(self.perecent_lines)

    def test_auto_transaction_abs(self):
        root, transactions = parse_file(self.abs_lines)


class AutoPeriodicTransactionTest(unittest.TestCase):
    lines = """
2000/01/01 Loaning someone money
    Loan:Car                                $10000
    Assets:Debit

~monthly
    .Loan:Car					       =$0
    Interest

= ^Loan:Car$
    .Loan:Car:Interest                        -.01
    Loan:Car					         -1

2000/02/01 FirstPayment
    Loan:Car:Payment                                -$100
    Assets:Debit
    """.splitlines()

    lines_shorthand = """
2000/01/01 Loaning someone money
    Assets:Debit
    Loan:Car                                $10000

I Loan:Car ~monthly -(.12 / 12) Interest :Interest

2000/02/01 FirstPayment
    Loan:Car:Payment                                -$100
    Assets:Debit
    """.splitlines()

    lines_shorthand_close = """
2000/01/01 Loaning someone money
    Assets:Debit
    Loan:Car                                $10000

I Loan:Car ~monthly -.1 Interest :Interest
C Interest Loan:Car

2000/02/01 FirstPayment
    Loan:Car:Payment                                -$100
    Assets:Debit
    """.splitlines()

    def test_loan(self):
        root, transactions = parse_file(self.lines)
        self.assertEqual(int(root.getAccount("Loan").getValue("$")), 10000)

    def test_loan_shorthand(self):
        root, transactions = parse_file(self.lines_shorthand)
        self.assertEqual(int(root.getAccount("Loan").getValue("$")), 10000)

    def test_loan_shorthand_close(self):
        root, transactions = parse_file(self.lines_shorthand_close)
        self.assertEqual(int(root.getAccount("Loan").getValue("$")), 10000 - 100)


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
% Comment
| Comment
* Comment
2000/01/03 Transaction 3
    Expenses:Food                           $300; Comment
    Assets:Credit                           =-$600
    """.splitlines()

    def test_parse_file(self):
        root, transactions = parse_file(self.lines)
        assert(root.children)
        assert(transactions)

    def test_parse_file_empty(self):
        root, transactions = parse_file([])

    def test_parse_file_end(self):
        lines = self.lines + ["2048/01/01 Bad date", "    JUNK $3"]
        self.assertRaises(Exception, parse_file, lines)
        parse_file(self.lines, end="2021")

    def test_subcommands(self):
        for cmd in ["balance", "register", "report"]:
            with self.subTest(cmd=cmd):
                parse_args([cmd], self.lines)
                parse_args([cmd[0]], self.lines)
                parse_args([cmd[:3]], self.lines)
                parse_args([cmd, "Assets"], self.lines)
                parse_args([cmd, "Assets", "Expenses"], self.lines)
                parse_args([cmd, "A", "E"], self.lines)


if __name__ == '__main__':

    unittest.main()
