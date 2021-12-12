#!/bin/python3
import argparse
import datetime
import logging
import os
import re
from collections import defaultdict
from decimal import Decimal
from string import whitespace

currency_regex = re.compile("[^\d\.\-\(\)\*\+\-/ ]+")


def getCurrencySymbol(token):
    match = currency_regex.search(token.strip())
    return match.group(0) if(match) else ""


class Account:

    def __init__(self, name="", parent=None):
        self.children = {}
        self.name = name
        self.parent = parent
        self.values = {}
        self.market = {}
        if parent:
            assert name
            self.parent.children[name] = self

    def getProperName(self):
        parentName = self.parent.getProperName() if self.parent else ""
        if parentName:
            parentName += ":"
        return parentName + self.name

    def __str__(self):
        return "Name:{} Children:{}".format(self.getProperName(), self.children)

    def __repr__(self):
        return str(self)

    def getRoot(self):
        return self if self.parent == None else self.parent.getRoot()

    def getDepth(self):
        return self.getProperName().count(":")

    def filterByDepth(self, depth):
        return depth is None or self.getDepth() < depth

    def getAccount(self, name):
        parent = self
        for component in name.split(":"):
            if component not in parent.children.keys():
                parent.children[component] = Account(component, parent)
            parent = parent.children.get(component)
            assert parent not in parent.children.values()

        return parent

    def addValue(self, currency, value, init=False):
        if value:
            assert isinstance(value, Decimal)
            if init:
                self.values[currency] = value
            else:
                self.values[currency] = self.values.get(currency, 0) + value

    def setMarketPrice(self, currency, c, value):
        self.market[currency] = value

    def getMarketPrice(self, currency, target):
        return 1 if currency == target else self.market[currency]

    def __getValue(self, currency):
        return self.values.get(currency, 0) + sum([children.__getValue(currency) for children in self.children.values()])

    def getSpecificValue(self, currency):
        return self.values.get(currency, 0)

    def getValue(self, currency):
        return round(self.__getValue(currency), 12)

    def getCurrencies(self):
        return set(self.values.keys()).union(*[children.getCurrencies() for children in self.children.values()])

    def matches(self, filter_strs):
        if not filter_strs:
            return True
        for filterStr in filter_strs:
            if re.match(filterStr, self.getProperName()):
                return True


class TransactionItem:
    def __init__(self, account, token=None, line_num=None):
        self.account = account
        self.values = {}
        self.postAccountValue = {}
        self.finalValue = None
        self.line_num = line_num
        self.__parse(token)

    def __str__(self):
        return "#{} {} {}".format(self.line_num, self.account.getProperName(), self.values)

    def __parse(self, token):
        if token:
            if isinstance(token, tuple):
                self.setValue(token[0], token[1])
            elif "@@" in token:
                parts = token.split("@@")
                value = Decimal(currency_regex.sub("", parts[0]))
                total_value = Decimal(currency_regex.sub("", parts[1])) * -abs(value) / value
                self.setValue(getCurrencySymbol(parts[0]), value)
                self.setValue(getCurrencySymbol(parts[1]), total_value)

                self.account.getRoot().setMarketPrice(getCurrencySymbol(parts[0]), getCurrencySymbol(parts[1]), -total_value / value)
            elif "@" in token:
                parts = token.split("@")
                value = Decimal(currency_regex.sub("", parts[0]))
                value_per_unit = Decimal(currency_regex.sub("", parts[1]))
                self.setValue(getCurrencySymbol(parts[0]), value)
                self.setValue(getCurrencySymbol(parts[1]), value * value_per_unit * -1)
                self.account.getRoot().setMarketPrice(getCurrencySymbol(parts[0]), getCurrencySymbol(parts[1]), value_per_unit)
            elif "=" in token:
                parts = token.split("=")

                self.finalValue = getCurrencySymbol(parts[1]), Decimal(currency_regex.sub("", parts[1]))
                if parts[0]:
                    self.__parse(parts[0])
            elif "(" in token:
                self.setValue(getCurrencySymbol(token), eval(currency_regex.sub("", token)))
            else:
                self.setValue(getCurrencySymbol(token), currency_regex.sub("", token))

    def getValue(self, currency):
        return self.values.get(currency, 0)

    def setValue(self, currency, value):
        assert currency not in self.values
        self.values[currency] = Decimal(value)

    def setPostAccountValue(self, c, value):
        self.postAccountValue[c] = value

    def getPostAccountValue(self, c):
        return self.postAccountValue[c]

    def isMissingValue(self):
        return not self.values

    def hasImplicitValue(self):
        return self.isMissingValue() and not self.finalValue

    def getCurrencies(self):
        return self.values.keys() if not self.finalValue else [self.finalValue[0]]

    def getSingleCurrency(self):
        return list(self.values.keys())[0]

    def isNetZero(self):
        return len(self.values.keys()) > 1

    def computeValueIfMissing(self):
        if self.isMissingValue() and self.finalValue:
            c, v = self.finalValue
            self.setValue(c, v - self.account.getValue(c))

    def postVerify(self):
        if self.finalValue:
            c, value = self.finalValue
            if abs(self.account.getValue(c) - value) > 1e-6:
                raise ValueError("Expected Value {} instead of {}".format(value, self.account.getValue(c)))


class AutoTransaction:
    def __init__(self, pattern, root):
        self.pattern = re.compile(pattern)
        self.root = root
        self.items = []

    def addItem(self, accountName, token=None, **kwargs):
        account = self.root.getAccount(accountName)
        item = TransactionItem(account, token, **kwargs)
        assert len(item.getCurrencies()) == 1
        item.currency = list(item.getCurrencies())[0]
        self.items.append((item, accountName))
        return item

    def matchesTransactionItem(self, item):
        return self.pattern.match(item.account.getProperName())

    def addToTransaction(self, transaction, refItem):
        assert not isinstance(transaction, AutoTransaction)
        refCurrency = refItem.getSingleCurrency()
        for item, accountName in self.items:
            c = item.getSingleCurrency()
            value = item.getValue(c) if c else item.getValue(c) * refItem.getValue(refCurrency)
            transaction.addItem(accountName, (c or refCurrency, value), line_num=item.line_num)


class Transaction:

    def __init__(self, date, title, root, line_num=None):
        self.items = []
        self.inferred_item = None
        self.date = date
        self.title = title.strip()
        self.initialize = self.title.startswith("*")
        self.root = root
        self.line_num = line_num

    def __lt__(self, other):
        return self.date < other.date

    def get_date_identifier(self, date_index):
        return "/".join(self.date.split("/")[:date_index + 1])

    def getHeader(self):
        return "#{} {} {}".format(self.line_num, self.date, self.title)

    def __repr__(self):
        return self.getHeader()

    def dump(self):
        print("Dumping: {} and {} items".format(self, len(self.items)))
        for item in self.items:
            print(item)

    def addItem(self, accountName, token=None, **kwargs):
        account = self.root.getAccount(accountName)
        item = TransactionItem(account, token, **kwargs)
        self.items.append(item)
        if item.hasImplicitValue():
            assert self.inferred_item is None
            self.inferred_item = item
        return item

    def commit(self):
        logging.debug("Committing %s", self.getHeader())
        currencies = {c for item in self.items for c in item.getCurrencies()}
        for item in self.items:
            item.computeValueIfMissing()
        for c in currencies:
            if not self.initialize:
                s = sum([item.getValue(c) for item in self.items if not item.isNetZero()])
                if self.inferred_item:
                    self.inferred_item.setValue(c, -s)
                    s = 0
                if s > 1e-6:
                    logging.error("Transaction doesn't balance %.02f '%s' %s", s, c, [item.getValue(c) for item in self.items])
                    raise ValueError("Transaction doesn't balance ")

            for item in self.items:
                item.account.addValue(c, item.getValue(c), self.initialize)
                item.setPostAccountValue(c, item.account.getValue(c))
                item.postVerify()


def print_balance(value, currency, name=None, depth=0):
    formatted_value = f"{value:-,.2f}"
    print(f"{formatted_value:>12s} {currency:>4s} " + ("\t" * depth) + (f"{name}" if name else ""))


def get_nested_accounts(parent, filterStr, running_total=None):
    for account in parent.children.values():
        if not filterStr or account.matches(filterStr):
            for c in account.getCurrencies():
                if account.getValue(c):
                    if not running_total is None:
                        running_total[c] = running_total.get(c, 0) + account.getSpecificValue(c)
            yield account
        yield from get_nested_accounts(account, filterStr, running_total)


def balance(root, transactions, filterStr=None, market=None, depth=None, **kwargs):
    running_total = {}
    for account in filter(lambda x: x.filterByDepth(depth), get_nested_accounts(root, filterStr, running_total=running_total)):
        if market:
            total = 0
            total = sum([account.getValue(c) * root.getMarketPrice(c, target=market) for c in account.getCurrencies() if account.getValue(c)])
            if total:
                print_balance(total, market, account.getProperName(), depth=account.getDepth())
        else:
            for c in account.getCurrencies():
                if account.getValue(c):
                    print_balance(account.getValue(c), c, account.getProperName(), depth=account.getDepth())
    if market in account.getCurrencies():
        total = sum([running_total[c] * root.getMarketPrice(c, target=market) for c in running_total.keys()])
        print_balance(total, market)
    else:
        for c in running_total:
            print_balance(running_total[c], c)
    return running_total


def register(root, transactions, filterStr=None, market=None, start=None, **kwargs):
    for transaction in transactions:
        for item in transaction.items:
            if not filterStr or item.account.matches(filterStr):
                for c in item.getCurrencies():
                    print("{:50.50s}\t{:20.20s}\t{:3.3s}{:-12.2f}\t{:3.3s}{:-12.2f}".format(transaction.getHeader(), item.account.getProperName(), c, item.getValue(c), c, item.getPostAccountValue(c)))


def report(root, transactions, filterStr=None, date_index=1, market="$", **kwargs):
    groups = defaultdict(lambda: 0)
    for transaction in transactions:
        key = transaction.get_date_identifier(date_index if date_index is not None else 1)
        for item in transaction.items:
            if not filterStr or item.account.matches(filterStr):
                if market:
                    groups[key] += sum([item.getValue(c) * root.getMarketPrice(c, target=market) for c in item.getCurrencies()])
                else:
                    for c in item.getCurrencies():
                        groups[key + c] += item.getValue(c)

    for key, value in groups.items():
        print(f"{key:.50s}, {value:-12.2f}")


def parse_args(args=None, lines=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", default=os.getenv("LEDGER_FILE"))

    parser.add_argument("--sorted", default=False, action="store_const", const=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--market", action="store_const", const="$")

    shared_parser = argparse.ArgumentParser(add_help=False)
    shared_parser.add_argument("accounts", default=None, nargs="*")

    sub_parsers = parser.add_subparsers(dest="type")

    balance_parser = sub_parsers.add_parser("balance", description="Report balance for accounts", aliases=["bal", "b"], parents=[shared_parser])

    balance_parser.add_argument("--depth", "-d", type=int)
    balance_parser.set_defaults(func=balance)

    register_parser = sub_parsers.add_parser("register", description="List items involving account", aliases=["reg", "r"], parents=[shared_parser])
    register_parser.set_defaults(func=register)

    report_parser = sub_parsers.add_parser("report", description="List items involving account", aliases=["rep"], parents=[shared_parser])
    report_parser.add_argument("--daily", "-d", action="store_const", const=2, dest="date_index")
    report_parser.add_argument("--monthly", "-m", action="store_const", const=1, dest="date_index")
    report_parser.add_argument("--yearly", "-y", action="store_const", const=0, dest="date_index")
    report_parser.set_defaults(func=report)

    namespace = parser.parse_args(args)
    ledger_file = namespace.file

    if lines:
        root, transactions = parse_file(lines, check_sorted=namespace.sorted, end=namespace.end)
    else:
        with open(ledger_file, "r") as f:
            root, transactions = parse_file(f, check_sorted=namespace.sorted, end=namespace.end)

    kwargs = {k: v for k, v in vars(namespace).items()}
    if kwargs.get("start") is not None:
        transactions = filter(lambda x: x.date < namespace.start, transactions)
    namespace.func(root, transactions, namespace.accounts, **kwargs,)


def next_date(date, index):
    if index == 0:
        return date.replace(year=date.year + 1)
    elif index == 1:
        try:
            return date.replace(month=date.month + 1)
        except ValueError:
            return date.replace(year=date.year + 1, month=1)
    elif index == 2:
        try:
            return date.replace(day=date.day + 1)
        except ValueError:
            return next_date(date.replace(day=1), 1)


def parse_file(f, root=None, check_sorted=False, end=None):
    if root is None:
        root = Account()

    transactions = []
    auto_transactions = []
    periodic_transactions = []
    t = None
    lastDate = None

    def helper(t, itemStr):
        item = t.addItem(itemStr[0], " ".join(itemStr[1:]), line_num=i)
        for auto_transaction in auto_transactions:
            if auto_transaction != t and auto_transaction.matchesTransactionItem(item):
                auto_transaction.addToTransaction(t, item)
    for i, line in enumerate(f):
        try:
            commentSplit = line.split(";")
            data, _ = commentSplit[0], commentSplit[1:]

            if data.strip():
                itemStr = data.split()
                if data[0] in whitespace:
                    if isinstance(t, list):
                        t.append(itemStr)
                    elif t:
                        helper(t, itemStr)

                elif data[0] in ";#%|*":  # is comment
                    pass
                elif data[0] == "~":  # is perodic expression; currently unsupported
                    if itemStr[0][1:] == "yearly":
                        index = 0
                        d = next_date(lastDate.replace(month=1), index)
                    elif itemStr[0][1:] == "monthly":
                        index = 1
                        d = next_date(lastDate.replace(day=1), index)
                    elif itemStr[0][1:] == "daily":
                        index = 2
                        d = next_date(lastDate, index)
                    t = []
                    periodic_transactions.append([d, data[1:], index, t])
                    periodic_transactions.sort()
                elif data[0] == "=":  # is automatic expression
                    t = AutoTransaction(" ".join(itemStr[1:]), root=root, )
                    auto_transactions.append(t)
                elif data[0] == "P":
                    _, date, currency, value = data.split()

                    v = Decimal(currency_regex.sub("", value))
                    c = getCurrencySymbol(value)
                    root.setMarketPrice(currency, c, v)
                elif data[0].isdigit():
                    if end is not None and itemStr[0] > end:
                        break
                    lastDate = datetime.date(*list(map(int, itemStr[0].split("/"))))
                    while periodic_transactions and lastDate >= periodic_transactions[0][0]:
                        t = Transaction(date=periodic_transactions[0][0].strftime('%Y/%m/%d'), title=periodic_transactions[0][1], root=root, line_num=i)
                        for args in periodic_transactions[0][-1]:
                            helper(t, args)
                        transactions.append(t)
                        periodic_transactions[0][0] = next_date(periodic_transactions[0][0], periodic_transactions[0][-2])
                        periodic_transactions.sort()
                    t = Transaction(date=itemStr[0], title=" ".join(itemStr[1:]), root=root, line_num=i)
                    if check_sorted and transactions:
                        if transactions[-1] > t:
                            logging.warning("Not sorted %s %s", transactions[-1], t)
                    transactions.append(t)
        except Exception as e:
            logging.error("Error processing line #%d %s", i, line)
            raise e

    for t in transactions:
        try:
            t.commit()
        except ValueError:
            t.dump()
            raise

    return root, transactions


if __name__ == "__main__":
    logging.basicConfig(format='[%(filename)s:%(lineno)s]%(levelname)s:%(message)s', level=logging.INFO)
    parse_args()
