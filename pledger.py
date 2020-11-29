import re

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

    def getAccount(self, name):
        parent = self
        for component in name.split(":"):
            if component not in parent.children.keys():
                parent.children[component] = Account(component, parent)
            parent = parent.children.get(component)
            assert parent not in parent.children.values()

        return parent

    def addValue(self, currency, value, init=False):
        if init:
            self.values[currency] = value
        else:
            self.values[currency] = self.values.get(currency, 0) + value

    def getValue(self, currency):
        return self.values.get(currency, 0) + sum([children.getValue(currency) for children in self.children.values()])


class TransactionItem:
    def __init__(self, account, token=None):
        self.values = {}
        self.account = account
        self.finalValue = None
        self.__parse(token)

    def __parse(self, token):
        if token:
            if "@" in token:
                parts = token.split("@")
                value = float(currency_regex.sub("", parts[0]))
                self.values[getCurrencySymbol(parts[0])] = value
                self.values[getCurrencySymbol(parts[1])] = value * float(currency_regex.sub("", parts[1])) * -1
            elif "=" in token:
                parts = token.split("=")

                self.finalValue = getCurrencySymbol(parts[1]), float(currency_regex.sub("", parts[1]))
                if parts[0]:
                    self.__parse(parts[0])
                else:
                    c, v = self.finalValue
                    self.values[c] = v - self.account.getValue(c)
            elif "(" in token:
                self.values[getCurrencySymbol(token)] = eval(currency_regex.sub("", token))
            else:
                self.values[getCurrencySymbol(token)] = float(currency_regex.sub("", token))

    def getValue(self, currency):
        return self.values.get(currency, 0)

    def setValue(self, currency, value):
        self.values[currency] = value

    def isMissingValue(self):
        return not self.values

    def postVerify(self):
        if self.finalValue:
            c, value = self.finalValue
            if self.account.getValue(c) != value:
                raise ValueError("Expected Value {} instead of {}".format(value, self.account.getValue(c)))


class Transaction:

    def __init__(self, date, title, root):
        self.items = []
        self.inferred_item = None
        self.date = date
        self.title = title.strip()
        self.initialize = self.title.startswith("*")
        self.root = root

    def __lt__(self, other):
        return self.date < other.date

    def addItem(self, accountName, token=None):
        account = self.root.getAccount(accountName)
        item = TransactionItem(account, token)
        self.items.append(item)
        if(item.isMissingValue()):
            assert self.inferred_item is None
            self.inferred_item = item

    def commit(self):
        currencies = {c for item in self.items for c in item.values.keys()}
        for c in currencies:
            if not self.initialize:
                s = sum([item.getValue(c) for item in self.items])
                if self.inferred_item:
                    self.inferred_item.setValue(c, -s)
                    s += -s
                assert s == 0
            for item in self.items:
                item.account.addValue(c, item.getValue(c), self.initialize)
        for item in self.items:
            item.postVerify()


def main(fileName="ledger"):
    with open(fileName, "r") as f:
        for line in f:
            parts = line.split(";")
            if parts[0]:
                pass


if __name__ == "__main__":
    pass
