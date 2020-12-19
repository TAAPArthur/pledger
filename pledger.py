import argparse
import os
import re
from string import whitespace
import logging
from decimal import Decimal

currency_regex = re.compile("[^\d\.\-\(\)\*\+\-/ ]+")


def getCurrencySymbol(token):
    match = currency_regex.search(token.strip())
    return match.group(0) if(match) else None


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
        return self.__getValue(currency)

    def getCurrencies(self):
        return self.values.keys()

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
            if "@@" in token:
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

    def isNetZero(self):
        return len(self.values.keys()) > 1

    def computeValueIfMissing(self):
        if self.isMissingValue() and self.finalValue:
            c, v = self.finalValue
            self.setValue(c, v - self.account.getValue(c))

    def postVerify(self):
        if self.finalValue:
            c, value = self.finalValue
            if self.account.getValue(c) != value:
                raise ValueError("Expected Value {} instead of {}".format(value, self.account.getValue(c)))


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

    def getHeader(self):
        return "#{} {} {}".format(self.line_num, self.date, self.title)

    def __repr__(self):
        return self.getHeader()

    def dump(self):
        print("Dumping: {} and {} items".format(self, len(self.items)))
        for item in self.items:
            print(item)

    def addItem(self, accountName, token=None, line_num=None):
        account = self.root.getAccount(accountName)
        item = TransactionItem(account, token, line_num)
        self.items.append(item)
        if item.hasImplicitValue():
            assert self.inferred_item is None
            self.inferred_item = item

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
                if s > 1e6:
                    logging.error("Transaction doesn't balance %d '%s' %s", s, c, [item.getValue(c) for item in self.items])
                    raise ValueError("Transaction doesn't balance ")

            for item in self.items:
                item.account.addValue(c, item.getValue(c), self.initialize)
                item.setPostAccountValue(c, item.account.getValue(c))
                item.postVerify()


def print_balance(value, currency, name=None):
    formatted_value = f"{value:-,.2f}"
    print(f"{formatted_value:>10s} {currency:>4s} " + (f"{name}" if name else ""))


def get_nested_accounts(parent, filterStr, running_total=None):
    for account in parent.children.values():
        if not filterStr or account.matches(filterStr):
            for c in account.getCurrencies():
                if account.getValue(c):
                    if not running_total is None:
                        running_total[c] = running_total.get(c, 0) + account.getSpecificValue(c)
            yield account
        yield from get_nested_accounts(account, filterStr, running_total)


def balance(root, transactions, filterStr=None, market=None):
    running_total = {}
    for account in get_nested_accounts(root, filterStr, running_total=running_total):
        if market:
            total = 0
            total = sum([account.getValue(c) * root.getMarketPrice(c, target=market) for c in account.getCurrencies() if account.getValue(c)])
            if total:
                print_balance(total, market, account.getProperName())
        else:
            for c in account.getCurrencies():
                if account.getValue(c):
                    print_balance(account.getValue(c), c, account.getProperName())
    if market in account.getCurrencies():
        total = sum([running_total[c] * root.getMarketPrice(c, target=market) for c in running_total.keys()])
        print_balance(total, market)
    else:
        for c in running_total:
            print_balance(running_total[c], c)
    return running_total


def register(root, transactions, filterStr=None, market=None):
    for transaction in transactions:
        for item in transaction.items:
            if not filterStr or item.account.matches(filterStr):
                for c in item.getCurrencies():
                    print("{}\t{}\t{}{:-12.2f}\t{}{:-12.2f}".format(transaction.getHeader(), item.account.getProperName(), c, item.getValue(c), c, item.getPostAccountValue(c)))


def parse_args(args=None, lines=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", default=os.getenv("LEDGER_FILE"))

    parser.add_argument("--sorted", default=False, action="store_const", const=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--market", "-m", action="store_const", const="$")
    parser.add_argument("type")
    parser.add_argument("accounts", nargs="*")
    namespace = parser.parse_args(args)
    ledger_file = namespace.file

    if lines:
        root, transactions = parse_file(lines, check_sorted=namespace.sorted)
    else:
        with open(ledger_file, "r") as f:
            root, transactions = parse_file(f, check_sorted=namespace.sorted)

    for func in [balance, register]:
        if func.__name__.startswith(namespace.type):
            func(root, transactions, namespace.accounts, market=namespace.market)
            break


def parse_file(f, root=Account(), check_sorted=False):

    transactions = []
    t = None
    for i, line in enumerate(f):
        try:
            commentSplit = line.split(";")
            data, comment = commentSplit[0], commentSplit[1:]
            if data.strip():
                itemStr = data.split()
                if data[0] in whitespace:
                    if t:
                        t.addItem(itemStr[0], " ".join(itemStr[1:]), line_num=i)
                elif data[0] in ";#%|*":  # is comment
                    pass
                elif data[0] == "~":  # is perodic expression; currently unsupported
                    t = None
                elif data[0] == "P":
                    _, date, currency, value = data.split()

                    v = Decimal(currency_regex.sub("", value))
                    c = getCurrencySymbol(value)
                    root.setMarketPrice(currency, c, v)
                elif data[0].isdigit():
                    t = Transaction(date=itemStr[0], title=" ".join(itemStr[1:]), root=root, line_num=i)
                    if check_sorted and transactions:
                        if transactions[-1] > t:
                            logging.warn("Not sorted %s %s", transactions[-1], t)
                    transactions.append(t)
        except Exception as e:
            logging.error("Error processing line #%d %s", i, line)
            raise e

    print(check_sorted)
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
