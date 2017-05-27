from lolicon.user import User

class Command:

    def __init__(self, name, trailing='', user=None):
        if not isinstance(name, str):
            raise TypeError('name must be str')
        if not isinstance(trailing, str):
            raise TypeError('trailing must be str')
        if user != None and not isinstance(user, User):
            raise TypeError('user must be User')

        self.name = name
        self.trailing = trailing
        self.user = user
